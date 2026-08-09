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
from app.orchestrator.rate_limiter import AsyncRateLimiter

ConnectorFactory = Callable[[], object]

# Security/compliance review finding: each factory call used to build its own
# `GenericConnector`, and `GenericConnector.__init__` defaults to a brand new
# `AsyncRateLimiter` when none is passed in - so two collections running
# concurrently against the same custom source (e.g. one started while another
# is still in progress) each got their own limiter and could double the
# configured `rate_limit_rps` against that source, the same class of bug the
# built-in connectors avoid via their module-level `OPENALEX_RATE_LIMITER` etc.
# singletons (app/orchestrator/rate_limiter.py). Keyed by slug + configured
# rate so an edited `rate_limit_rps` takes effect on the next collection
# rather than being stuck behind a stale limiter from before the edit.
_RATE_LIMITERS: dict[tuple[str, float], AsyncRateLimiter] = {}


def _shared_rate_limiter(slug: str, rate_limit_rps: float) -> AsyncRateLimiter:
    key = (slug, rate_limit_rps)
    limiter = _RATE_LIMITERS.get(key)
    if limiter is None:
        limiter = AsyncRateLimiter(1 / rate_limit_rps)
        _RATE_LIMITERS[key] = limiter
    return limiter


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
    return lambda: GenericConnector(
        slug=slug,
        config=config,
        rate_limiter=_shared_rate_limiter(slug, config.rate_limit_rps),
    )
