from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.entities import CollectionStatus


class SourceId(str, Enum):
    arxiv = "arxiv"
    openalex = "openalex"
    crossref = "crossref"
    pubmed = "pubmed"
    semantic_scholar = "semantic_scholar"


_MAX_KEYWORDS = 50
"""
Hard ceiling on how many keywords one collection can carry (security review
finding: `keywords` had no bound at all, so a request could queue an
arbitrarily long sequential fan-out - `app.orchestrator.runner` runs a
source's keywords one at a time - hammering every selected source far past
what the per-source rate limiter's steady-state RPS implies and tying up a
BackgroundTask indefinitely). 50 is generous headroom over the "5 keywords"
scale used throughout the stories/tests while still being a real bound.
"""


class CollectionParamsRequest(BaseModel):
    keywords: list[str] = Field(default_factory=list, max_length=_MAX_KEYWORDS)
    # str rather than list[SourceId]: a request may also name a custom
    # connector's slug (EP-custom-connectors), which isn't one of the fixed
    # built-in ids. Nothing here needs to know custom sources exist -
    # `app.orchestrator.runner.run_collection` already handles any source
    # string it doesn't have a factory for by marking it failed without
    # blocking the others, which is exactly the right behavior for a source
    # slug that was since disabled/deleted.
    sources: list[str] = Field(max_length=50)
    max_articles_per_keyword: int = Field(ge=10, le=100)
    year_from: int | None = Field(default=None, ge=1900)
    year_to: int | None = Field(default=None, ge=1900)

    # Optional filters - applied when the underlying source exposes the field.
    language: str | None = Field(default=None, max_length=50)
    domain: str | None = Field(default=None, max_length=100)

    # Never silently drop data by default (matches Collection Charter B.3/B.4).
    include_missing_abstract: bool = True
    exclude_duplicates_on_export: bool = True

    @field_validator("sources")
    @classmethod
    def at_least_one_source(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("Select at least one source.")
        return v

    @field_validator("keywords")
    @classmethod
    def keywords_are_reasonably_sized(cls, v: list[str]) -> list[str]:
        # `Field(max_length=...)` on a list[str] only bounds the list itself
        # - each element was otherwise an unbounded string (security review
        # finding, same DoS-via-unbounded-input class as KeywordParseRequest).
        if any(len(kw) > 200 for kw in v):
            raise ValueError("Each keyword must be 200 characters or fewer.")
        return v

    @model_validator(mode="after")
    def year_range_is_valid(self) -> "CollectionParamsRequest":
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise ValueError("year_from must not be after year_to.")
        return self


class CollectionParamsSummary(BaseModel):
    selected_keywords: int
    active_sources: int
    max_potential_yield: int
    estimated_runtime_seconds: int


class CollectionParamsResponse(BaseModel):
    valid: bool = True
    summary: CollectionParamsSummary


class StartCollectionResponse(BaseModel):
    id: str
    status: CollectionStatus = CollectionStatus.RUNNING


class SourceProgressItem(BaseModel):
    source: str
    status: Literal["pending", "running", "done", "failed"]
    detail: str | None = None
    articles_fetched: int = 0


class CollectionProgressResponse(BaseModel):
    id: str
    status: CollectionStatus
    overall_progress: float
    current_keyword: str | None
    elapsed_seconds: int
    sources: list[SourceProgressItem]
    warning: str | None
    error: str | None
