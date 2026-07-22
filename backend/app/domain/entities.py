from datetime import datetime
from enum import StrEnum
from typing import Optional


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
    url: str | None = None
    doi: str | None = None
    venue: str | None = None
    domain: str | None = None
    categories: list[str] = Field(default_factory=list)
    citation_count: Optional[int] = None

    source: SourceEnum
    search_keyword: str
    collection_date: datetime


class ConnectorError(Exception):
    """
    Raised by a connector when a request to a source fails after the
    resilient HTTP layer's retries are exhausted (US-03.6). Carries the
    fields the orchestrator logs before continuing with other sources
    (US-03.4: one source failing must not block the others).
    """

    def __init__(self, *, source: SourceEnum, endpoint: str, keyword: str, error_class: str, message: str):
        self.source = source
        self.endpoint = endpoint
        self.keyword = keyword
        self.error_class = error_class
        super().__init__(message)
