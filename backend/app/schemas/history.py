from datetime import datetime

from pydantic import BaseModel

from app.domain.entities import CollectionStatus


class CollectionHistoryItem(BaseModel):
    id: str
    keywords: list[str]
    sources: list[str]
    article_count: int
    duplicate_count: int
    created_at: datetime
    status: CollectionStatus


class Pagination(BaseModel):
    total: int
    page: int
    page_size: int


class CollectionHistoryResponse(BaseModel):
    data: list[CollectionHistoryItem]
    pagination: Pagination
    sort: str
    filters: dict[str, str]
