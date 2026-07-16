from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Optional


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


@dataclass
class RawArticle:
    """Connector output before normalization (US-04.1 cleans/normalizes it)."""

    source: SourceEnum
    search_keyword: str
    collection_date: datetime
    title: Optional[str] = None
    authors_raw: Optional[list[str]] = None
    year: Optional[int] = None
    abstract: Optional[str] = None
    doi: Optional[str] = None
    venue: Optional[str] = None
    citation_count: Optional[int] = None
    url: Optional[str] = None
    domain: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


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
