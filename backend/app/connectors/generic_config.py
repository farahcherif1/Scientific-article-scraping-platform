"""
Config-driven connector schema + dot-path resolver for custom connectors
(EP-custom-connectors). Pure, zero-I/O module - unit-testable without a
network/DB, same rule as `app/domain/*` - so it lives separately from
`app/connectors/generic.py`, which does the actual HTTP work.

Design note: this schema is deliberately generic rather than an exhaustive
model of any one API. Researching IEEE Xplore, HAL, DOAJ, CORE and Europe
PMC (docs/custom-connectors.md has the full comparison) showed three axes of
real variation that a config needs to express to cover new JSON sources
without code changes:
  - auth style: none / API key in a header / API key in a query param
  - pagination style: page number, offset, or cursor/token
  - response shape: fields can be flat or nested, and array-valued (author
    lists, category lists) at any depth

The dot-path mini-DSL (`resolve_path`) covers all five researched sources'
field locations with one small piece of code instead of five bespoke
mappers - see the worked examples in each function's docstring.
"""
from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

_ARRAY_SEGMENT = re.compile(r"^(?P<key>[^\[\]]*)\[(?P<index>\*|\d*)\]$")


def resolve_path(payload: Any, path: str | None) -> Any:
    """
    Resolve a dot-path against a JSON-like structure (dicts/lists).

    Path grammar (each `.`-separated segment is one of):
      - `key`        -> dict lookup: current[key]
      - `key[]`      -> current[key] must be a list; map over every element
                        (the rest of the path, if any, is resolved against
                        each element and the results are collected)
      - `key[N]`     -> current[key] must be a list; take index N
      - `[]`         -> current itself is the list to map over (used when
                        the array sits at the root, e.g. results_path="[]")

    Returns a scalar/dict/list if the resolved path yields exactly one
    value (no `[]` anywhere in the path), or a list of resolved values if
    an array segment was expanded. Returns None if any segment is missing.

    Examples (see docs/custom-connectors.md for the source each mirrors):
      resolve_path({"bibjson": {"title": "X"}}, "bibjson.title") -> "X"
      resolve_path({"authors": [{"name": "A"}, {"name": "B"}]},
                   "authors[].name") -> ["A", "B"]
      resolve_path({"authFullName_s": ["A", "B"]}, "authFullName_s")
          -> ["A", "B"]  (already a flat array, no [] needed)
      resolve_path({"authors": {"authors": [{"full_name": "A"}]}},
                   "authors.authors[].full_name") -> ["A"]
    """
    if not path:
        return None

    current: list[Any] = [payload]
    expands = False  # True once a `[]`/`[*]` wildcard segment fans out into multiple values
    for segment in path.split("."):
        match = _ARRAY_SEGMENT.match(segment)
        next_current: list[Any] = []
        for item in current:
            if item is None:
                continue
            if match:
                key, index = match.group("key"), match.group("index")
                value = item.get(key) if key else item
                if not isinstance(value, list):
                    continue
                if index in ("", "*"):
                    expands = True
                    next_current.extend(value)
                else:
                    i = int(index)
                    if 0 <= i < len(value):
                        next_current.append(value[i])
            elif isinstance(item, dict):
                next_current.append(item.get(segment))
            else:
                next_current.append(None)
        current = next_current

    if not current:
        return None
    if not expands:
        return current[0]
    return current


class AuthType(StrEnum):
    NONE = "none"
    API_KEY_HEADER = "api_key_header"
    API_KEY_QUERY_PARAM = "api_key_query_param"


class PaginationStyle(StrEnum):
    PAGE = "page"
    OFFSET = "offset"
    CURSOR = "cursor"
    NONE = "none"  # source returns a single page; no pagination is attempted


class AuthConfig(BaseModel):
    type: AuthType = AuthType.NONE
    key_name: str | None = None
    """Header name (api_key_header) or query param name (api_key_query_param)."""
    key_value: str | None = None
    """
    The actual key/token value. Stored as plaintext in the `custom_connectors`
    JSON config column - see docs/custom-connectors.md "Limitations" for why
    (no secrets vault in the MVP) and what that implies operationally.
    """

    @field_validator("key_name", "key_value")
    @classmethod
    def _required_together(cls, v: str | None) -> str | None:
        return v.strip() if v else v


class QueryMapping(BaseModel):
    keyword_param: str = Field(min_length=1)
    """Query param that carries the search keyword, e.g. "q", "query", "querytext"."""
    year_from_param: str | None = None
    year_to_param: str | None = None
    static_params: dict[str, str] = Field(default_factory=dict)
    """Constant params sent on every request, e.g. {"format": "json"}."""


class PaginationConfig(BaseModel):
    style: PaginationStyle = PaginationStyle.NONE
    page_size: int = Field(default=20, ge=1, le=200)
    page_size_param: str | None = None

    # style = page
    page_param: str | None = None
    start_page: int = 1

    # style = offset
    offset_param: str | None = None
    start_offset: int = 0

    # style = cursor
    cursor_param: str | None = None
    next_cursor_path: str | None = None
    """Dot-path (resolve_path) to the next cursor/token in the response body."""

    results_path: str = Field(min_length=1)
    """Dot-path to the array of result records in the response body."""
    total_path: str | None = None
    """Optional dot-path to a total-hit count, used to stop pagination cleanly."""
    stop_when_empty: bool = True
    """
    Treat a page shorter than page_size as the last page. Needed for sources
    (e.g. HAL, CORE) that don't return a total count or a next-page token.
    """


class FieldMapping(BaseModel):
    path: str | None = None
    """Dot-path (resolve_path) into a single result record. None = not available."""
    default: Any = None


class FieldMappingConfig(BaseModel):
    title: FieldMapping
    authors: FieldMapping = Field(default_factory=lambda: FieldMapping())
    year: FieldMapping = Field(default_factory=lambda: FieldMapping())
    abstract: FieldMapping = Field(default_factory=lambda: FieldMapping())
    doi: FieldMapping = Field(default_factory=lambda: FieldMapping())
    citation_count: FieldMapping = Field(default_factory=lambda: FieldMapping())
    url: FieldMapping = Field(default_factory=lambda: FieldMapping())
    venue: FieldMapping = Field(default_factory=lambda: FieldMapping())


class CustomConnectorConfig(BaseModel):
    """The full, persisted configuration for one custom connector."""

    base_url: str = Field(min_length=1)
    http_method: str = Field(default="GET", pattern="^(GET|POST)$")
    auth: AuthConfig = Field(default_factory=AuthConfig)
    query_mapping: QueryMapping
    pagination: PaginationConfig
    field_mapping: FieldMappingConfig
    headers: dict[str, str] = Field(default_factory=dict)
    """Static headers sent on every request, in addition to auth/User-Agent."""

    rate_limit_rps: float = Field(default=1.0, gt=0, le=50)
    connect_timeout_s: float = Field(default=10.0, gt=0)
    read_timeout_s: float = Field(default=30.0, gt=0)

    @field_validator("base_url")
    @classmethod
    def _base_url_looks_like_url(cls, v: str) -> str:
        if not re.match(r"^https?://", v.strip(), re.IGNORECASE):
            raise ValueError("base_url must start with http:// or https://")
        return v.strip()
