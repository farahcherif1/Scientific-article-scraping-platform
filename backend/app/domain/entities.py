from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class CollectionStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    WARNING = "warning"
    FAILED = "failed"

class SourceEnum(StrEnum):
    OPENALEX = "openalex"
    ARXIV = "arxiv"
    CROSSREF = "crossref"
    PUBMED = "pubmed"
    SEMANTIC_SCHOLAR = "semantic_scholar"

class RawArticle(BaseModel):
    """
    Common bibliographic schema every connector maps into before
    cleaning / deduplication .
    """

    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    abstract: str | None = None
    keywords: list[str] = Field(default_factory=list)
    url: str | None = None
    doi: str | None = None
    venue: str | None = None
    domain: str | None = None
    categories: list[str] = Field(default_factory=list)
    citation_count: int | None = None

    # str rather than SourceEnum: built-in connectors still pass a SourceEnum
    # member (StrEnum, so it satisfies `str` identically), but a custom
    # connector (US-EP-custom-connectors) identifies itself by its
    # user-defined slug, which isn't one of the fixed enum members. Nothing
    # downstream (compliance/cleaning/dedup/ranking) branches on the enum
    # type - it's only ever used as a plain grouping/display string - so
    # this widening is safe.
    source: str
    search_keyword: str
    collection_date: datetime


class ArticleClean(BaseModel):
    """
    Normalized bibliographic record produced by `app.domain.cleaning`
    (US-04.1) from a `RawArticle`. Missing fields are kept as `None` and
    listed in `missing_fields` rather than dropped, so downstream consumers
    (ranking, export, UI badges) can distinguish "absent" from "not yet
    normalized".
    """

    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    abstract: str | None = None
    url: str | None = None
    doi: str | None = None
    venue: str | None = None
    domain: str | None = None
    categories: list[str] = Field(default_factory=list)
    citation_count: int | None = None
    keywords: list[str] = Field(default_factory=list)
    keywords_auto: list[str] = Field(default_factory=list)

    source: str
    search_keyword: str
    collection_date: datetime

    duplicate_group_id: str | None = None
    duplicate_similarity_score: int | None = None
    duplicate_rule: str | None = None
    is_duplicate: bool = False

    missing_fields: list[str] = Field(default_factory=list)


class ConnectorError(Exception):
    """
    Raised by a connector when a request to a source fails after the
    resilient HTTP layer's retries are exhausted (US-03.6). Carries the
    fields the orchestrator logs before continuing with other sources
    (US-03.4: one source failing must not block the others).
    """

    def __init__(self, *, source: str, endpoint: str, keyword: str, error_class: str, message: str):
        self.source = source
        self.endpoint = endpoint
        self.keyword = keyword
        self.error_class = error_class
        super().__init__(message)
