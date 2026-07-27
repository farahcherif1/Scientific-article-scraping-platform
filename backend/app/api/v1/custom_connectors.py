from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.connectors.generic import GenericConnector
from app.connectors.generic_config import CustomConnectorConfig
from app.db.session import get_db
from app.schemas.custom_connectors import (
    CustomConnectorCreateRequest,
    CustomConnectorHealthResponse,
    CustomConnectorListResponse,
    CustomConnectorResponse,
    CustomConnectorTestRequest,
    CustomConnectorTestResponse,
    Pagination,
)
from app.use_cases.manage_custom_connectors import (
    create_custom_connector,
    delete_custom_connector,
    get_custom_connector,
    list_custom_connectors,
    test_custom_connector,
    update_custom_connector,
)

router = APIRouter(prefix="/custom-connectors", tags=["custom-connectors"])


def _to_response(row) -> CustomConnectorResponse:
    config = CustomConnectorConfig.model_validate(row.config)
    auth_key_configured = bool(config.auth.key_value)
    # This endpoint has no auth (same as every other endpoint in this app -
    # see docs/limitations.md), so a stored third-party API key must never
    # round-trip out through it in plaintext.
    redacted_config = config.model_copy(
        update={"auth": config.auth.model_copy(update={"key_value": None})}
    )
    return CustomConnectorResponse(
        id=row.slug,
        name=row.name,
        config=redacted_config,
        auth_key_configured=auth_key_configured,
        enabled=row.enabled,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/test", response_model=CustomConnectorTestResponse)
async def test_connection(payload: CustomConnectorTestRequest) -> CustomConnectorTestResponse:
    """
    Runs one live sample query against the configured (not-yet-saved) source.
    A source-side failure (bad URL, auth rejected, timeout) is returned as
    `success: false` with an `error` message rather than an HTTP error -
    that's the expected outcome of a "test connection" click, not a bug in
    this endpoint.
    """
    return await test_custom_connector(payload)


@router.get("", response_model=CustomConnectorListResponse)
def list_connectors(db: Session = Depends(get_db)) -> CustomConnectorListResponse:
    rows = list_custom_connectors(db)
    items = [_to_response(row) for row in rows]
    return CustomConnectorListResponse(
        data=items,
        pagination=Pagination(total=len(items), page=1, page_size=len(items) or 50),
        sort="-created_at",
        filters={},
    )


@router.post("", response_model=CustomConnectorResponse, status_code=201)
def create_connector(
    payload: CustomConnectorCreateRequest, db: Session = Depends(get_db)
) -> CustomConnectorResponse:
    row = create_custom_connector(db, payload)
    return _to_response(row)


@router.get("/{slug}", response_model=CustomConnectorResponse)
def get_connector(slug: str, db: Session = Depends(get_db)) -> CustomConnectorResponse:
    row = get_custom_connector(db, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown custom connector.")
    return _to_response(row)


@router.put("/{slug}", response_model=CustomConnectorResponse)
def update_connector(
    slug: str, payload: CustomConnectorCreateRequest, db: Session = Depends(get_db)
) -> CustomConnectorResponse:
    row = update_custom_connector(db, slug, payload)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown custom connector.")
    return _to_response(row)


@router.delete("/{slug}", status_code=204)
def delete_connector(slug: str, db: Session = Depends(get_db)) -> None:
    deleted = delete_custom_connector(db, slug)
    if not deleted:
        raise HTTPException(status_code=404, detail="Unknown custom connector.")


@router.get("/{slug}/health", response_model=CustomConnectorHealthResponse)
async def check_health(slug: str, db: Session = Depends(get_db)) -> CustomConnectorHealthResponse:
    row = get_custom_connector(db, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown custom connector.")
    config = CustomConnectorConfig.model_validate(row.config)
    connector = GenericConnector(slug=slug, config=config)
    try:
        healthy = await connector.health_check()
    finally:
        await connector.aclose()
    return CustomConnectorHealthResponse(id=slug, healthy=healthy)
