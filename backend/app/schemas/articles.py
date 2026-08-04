from datetime import datetime
from typing import Literal

from pydantic import BaseModel

SortField = Literal[
    "relevance", "-relevance", "year", "-year", "citation_count", "-citation_count"
]


class ArticleItem(BaseModel):
    id: int
    title: str
    authors: list[str]
    year: int | None
    abstract: str | None
    url: str | None
    doi: str | None
    venue: str | None
    domain: str | None
    categories: list[str]
    citation_count: int | None
    source: str
    search_keyword: str
    collection_date: datetime
    duplicate_group_id: str | None
    is_duplicate: bool
    missing_fields: list[str]
    relevance_score: int
    text_unified: str
    abstract_missing: bool


class ArticlesPagination(BaseModel):
    total: int
    page: int
    page_size: int


class ArticlesResponse(BaseModel):
    data: list[ArticleItem]
    pagination: ArticlesPagination
    sort: str
    filters: dict[str, str | int | bool | None]


class PerSourceStat(BaseModel):
    source: str
    count: int
    pct_with_doi: float
    pct_with_abstract: float
    pct_with_year: float


class YearCount(BaseModel):
    year: int
    count: int


class CollectionStatsResponse(BaseModel):
    total: int
    deduped: int
    duplicates: int
    pct_with_doi: float
    pct_with_abstract: float
    per_source: list[PerSourceStat]
    articles_per_year: list[YearCount]
