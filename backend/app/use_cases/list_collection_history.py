from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CollectionRun


def list_collection_history(db: Session) -> list[CollectionRun]:
    stmt = select(CollectionRun).order_by(
        CollectionRun.created_at.desc(), CollectionRun.id.desc()
    )
    return list(db.scalars(stmt))
