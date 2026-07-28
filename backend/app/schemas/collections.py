from enum import Enum
from typing import Literal
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.entities import CollectionStatus


class SourceId(str, Enum):
    arxiv = "arxiv"
    openalex = "openalex"
    crossref = "crossref"
    pubmed = "pubmed"
    semantic_scholar = "semantic_scholar"


class CollectionParamsRequest(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    # str rather than list[SourceId]: a request may also name a custom
    # connector's slug (EP-custom-connectors), which isn't one of the fixed
    # built-in ids. Nothing here needs to know custom sources exist -
    # `app.orchestrator.runner.run_collection` already handles any source
    # string it doesn't have a factory for by marking it failed without
    # blocking the others, which is exactly the right behavior for a source
    # slug that was since disabled/deleted.
    sources: list[str]
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


class QualityReportStats(BaseModel):
    title: float
    year: float
    doi: float
    abstract: float
    duplicate_rate: float


class CollectionQualityReport(BaseModel):
    overall: QualityReportStats
    sources: dict[str, QualityReportStats]


class CollectionDetailResponse(BaseModel):
    id: str
    keywords: list[str]
    sources: list[str]
    article_count: int
    duplicate_count: int
    quality_report: CollectionQualityReport
    created_at: datetime
    status: CollectionStatus
