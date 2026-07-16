from enum import StrEnum


from datetime import datetime

from pydantic import BaseModel, Field


class CollectionStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    WARNING = "warning"
    FAILED = "failed"


class RawArticle(BaseModel):
    """
    Common bibliographic schema every connector maps into before
    cleaning / deduplication (see Appendix A - Data Dictionary).
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

    source: str
    search_keyword: str
    collection_date: datetime
