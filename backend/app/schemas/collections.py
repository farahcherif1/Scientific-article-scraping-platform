from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class SourceId(str, Enum):
    arxiv = "arxiv"
    openalex = "openalex"
    crossref = "crossref"
    semantic_scholar = "semantic_scholar"


class CollectionParamsRequest(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    sources: list[SourceId]
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
    def at_least_one_source(cls, v: list[SourceId]) -> list[SourceId]:
        if not v:
            raise ValueError("Select at least one source.")
        return v

    @model_validator(mode="after")
    def year_range_is_valid(self) -> "CollectionParamsRequest":
        if self.year_from is not None and self.year_to is not None:
            if self.year_from > self.year_to:
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
