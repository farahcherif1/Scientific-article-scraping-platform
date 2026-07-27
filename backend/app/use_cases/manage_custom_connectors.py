"""
CRUD + test-connection use cases for custom connectors (EP-custom-connectors).
Kept out of the API layer (Clean Architecture: api -> use_cases) so the
route handlers in app/api/v1/custom_connectors.py stay thin adapters, same
split as app/use_cases/start_collection.py.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.connectors.generic import GenericConnector
from app.db.models import CustomConnector
from app.domain.entities import ConnectorError
from app.schemas.collections import SourceId
from app.schemas.custom_connectors import (
    CustomConnectorCreateRequest,
    CustomConnectorTestRequest,
    CustomConnectorTestResponse,
    RawArticlePreview,
)

_SLUG_MAX_LEN = 64
_NON_SLUG_CHARS = re.compile(r"[^a-z0-9]+")


class SlugConflictError(Exception):
    """Raised when no available slug could be derived from the given name."""


def slugify(name: str) -> str:
    base = _NON_SLUG_CHARS.sub("_", name.strip().lower()).strip("_")
    return (base or "custom")[:_SLUG_MAX_LEN]


def _reserved_slugs(db: Session, *, exclude_id: int | None = None) -> set[str]:
    reserved = {source.value for source in SourceId}
    query = db.query(CustomConnector.slug)
    if exclude_id is not None:
        query = query.filter(CustomConnector.id != exclude_id)
    reserved.update(slug for (slug,) in query.all())
    return reserved


def generate_unique_slug(db: Session, name: str, *, exclude_id: int | None = None) -> str:
    reserved = _reserved_slugs(db, exclude_id=exclude_id)
    base = slugify(name)
    if base not in reserved:
        return base
    for suffix in range(2, 1000):
        candidate = f"{base}-{suffix}"[:_SLUG_MAX_LEN]
        if candidate not in reserved:
            return candidate
    raise SlugConflictError(f"Could not derive a unique slug from '{name}'.")


def list_custom_connectors(db: Session) -> list[CustomConnector]:
    return db.query(CustomConnector).order_by(CustomConnector.created_at.desc()).all()


def get_custom_connector(db: Session, slug: str) -> CustomConnector | None:
    return db.query(CustomConnector).filter_by(slug=slug).first()


def create_custom_connector(
    db: Session, payload: CustomConnectorCreateRequest, *, created_by: str | None = None
) -> CustomConnector:
    slug = generate_unique_slug(db, payload.name)
    row = CustomConnector(
        name=payload.name,
        slug=slug,
        config=payload.config.model_dump(mode="json"),
        enabled=payload.enabled,
        created_by=created_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_custom_connector(
    db: Session, slug: str, payload: CustomConnectorCreateRequest
) -> CustomConnector | None:
    row = get_custom_connector(db, slug)
    if row is None:
        return None
    row.name = payload.name
    row.config = payload.config.model_dump(mode="json")
    row.enabled = payload.enabled
    db.commit()
    db.refresh(row)
    return row


def delete_custom_connector(db: Session, slug: str) -> bool:
    row = get_custom_connector(db, slug)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


async def test_custom_connector(payload: CustomConnectorTestRequest) -> CustomConnectorTestResponse:
    """
    Runs one live sample query against the configured source, entirely
    outside persistence - the researcher can iterate on field mapping
    before ever saving a `CustomConnector` row.
    """
    connector = GenericConnector(slug="test-connection", config=payload.config)
    try:
        result = await connector.test_connection(payload.keyword, payload.max_results)
    except ConnectorError as exc:
        return CustomConnectorTestResponse(
            success=False,
            error=f"{exc.error_class}: {exc}",
        )
    finally:
        await connector.aclose()

    return CustomConnectorTestResponse(
        success=True,
        status_code=result["status_code"],
        request_url=result["request_url"],
        raw_response=result["raw_response"],
        sample_records=result["sample_records"],
        mapped_articles=[
            RawArticlePreview(
                title=article.title,
                authors=article.authors,
                year=article.year,
                abstract=article.abstract,
                doi=article.doi,
                venue=article.venue,
                citation_count=article.citation_count,
                url=article.url,
            )
            for article in result["mapped_articles"]
        ],
    )
