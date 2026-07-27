"""
Merges the built-in connector factories with custom, DB-persisted ones
(EP-custom-connectors) into one dict. `app/orchestrator/runner.py` already
treats any dict entry identically (calls `.search()` / `.aclose()` on
whatever the factory returns) - so a custom connector's slug reaching this
dict is the entire integration; nothing in the orchestrator changes.
"""
from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.connectors.generic import GenericConnector
from app.connectors.generic_config import CustomConnectorConfig
from app.db.models import CustomConnector

ConnectorFactory = Callable[[], object]


def load_custom_connector_factories(db: Session) -> dict[str, ConnectorFactory]:
    """
    Enabled custom connectors only. A disabled one is simply absent from the
    dict, so a request naming it hits the orchestrator's existing
    "unregistered source" handling (fails that source, doesn't block others)
    without any custom-connector-specific logic there.
    """
    rows = db.query(CustomConnector).filter_by(enabled=True).all()
    return {row.slug: _make_factory(row.slug, row.config) for row in rows}


def _make_factory(slug: str, raw_config: dict) -> ConnectorFactory:
    config = CustomConnectorConfig.model_validate(raw_config)
    return lambda: GenericConnector(slug=slug, config=config)
