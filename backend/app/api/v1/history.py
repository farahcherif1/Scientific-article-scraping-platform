from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.history import CollectionHistoryItem, CollectionHistoryResponse, Pagination
from app.use_cases.list_collection_history import list_collection_history

router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=CollectionHistoryResponse)
def get_history(db: Session = Depends(get_db)) -> CollectionHistoryResponse:
    runs = list_collection_history(db)
    items = [
        CollectionHistoryItem(
            id=run.public_id,
            keywords=run.keywords,
            sources=run.sources,
            article_count=run.article_count,
            duplicate_count=run.duplicate_count,
            created_at=run.created_at,
            status=run.status,
        )
        for run in runs
    ]
    return CollectionHistoryResponse(
        data=items,
        pagination=Pagination(total=len(items), page=1, page_size=len(items) or 50),
        sort="-created_at",
        filters={},
    )
