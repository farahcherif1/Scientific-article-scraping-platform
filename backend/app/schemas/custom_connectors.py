from datetime import datetime

from pydantic import BaseModel, Field

from app.connectors.generic_config import CustomConnectorConfig

_SLUG_MAX_LEN = 64


class CustomConnectorCreateRequest(BaseModel):
    """Also used for PUT (full-replace update) - same shape either way."""

    name: str = Field(min_length=1, max_length=200)
    config: CustomConnectorConfig
    enabled: bool = True


class CustomConnectorResponse(BaseModel):
    id: str
    """The connector's slug - what appears in `CollectionParamsRequest.sources`."""
    name: str
    config: CustomConnectorConfig
    enabled: bool
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class Pagination(BaseModel):
    total: int
    page: int
    page_size: int


class CustomConnectorListResponse(BaseModel):
    data: list[CustomConnectorResponse]
    pagination: Pagination
    sort: str
    filters: dict[str, str]


class CustomConnectorTestRequest(BaseModel):
    config: CustomConnectorConfig
    keyword: str = Field(default="test", min_length=1, max_length=200)
    max_results: int = Field(default=3, ge=1, le=20)


class RawArticlePreview(BaseModel):
    title: str
    authors: list[str]
    year: int | None
    abstract: str | None
    doi: str | None
    venue: str | None
    citation_count: int | None
    url: str | None


class CustomConnectorTestResponse(BaseModel):
    success: bool
    status_code: int | None = None
    request_url: str | None = None
    raw_response: object | None = None
    sample_records: list[object] = Field(default_factory=list)
    mapped_articles: list[RawArticlePreview] = Field(default_factory=list)
    error: str | None = None


class CustomConnectorHealthResponse(BaseModel):
    id: str
    healthy: bool
