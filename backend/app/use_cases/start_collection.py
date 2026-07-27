"""
Start-collection use case (US-03.4 T-03.4.1).

Wires the API layer's FastAPI BackgroundTask to the orchestrator fan-out
loop (app.orchestrator.runner) and persists the run summary to
`collection_runs` once it finishes. Split out from the API module so the
route handler stays a thin adapter (Clean Architecture: api -> use_cases).
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.connectors.arxiv import ArxivConnector
from app.connectors.base import SearchFilters
from app.connectors.crossref import CrossrefConnector
from app.connectors.openalex import OpenAlexConnector
from app.connectors.pubmed import PubMedConnector
from app.connectors.semantic_scholar import SemanticScholarConnector
from app.db.models import CollectionRun
from app.db.session import SessionLocal
from app.domain.entities import CollectionStatus
from app.orchestrator import state as state_store
from app.orchestrator.runner import run_collection
from app.schemas.collections import CollectionParamsRequest

logger = logging.getLogger("app.use_cases.start_collection")

# Only sources with a real connector can run; any other SourceId is
# reported as a failed source by the orchestrator without blocking the others.
CONNECTOR_FACTORIES: dict[str, object] = {
    "arxiv": lambda: ArxivConnector(),
    "openalex": lambda: OpenAlexConnector(polite_pool_email=settings.polite_pool_email),
    "crossref": lambda: CrossrefConnector(),
    "pubmed": lambda: PubMedConnector(),
    "semantic_scholar": lambda: SemanticScholarConnector(),
}

# BackgroundTasks run outside request scope, so the final-state write can't
# go through FastAPI's `Depends(get_db)` override machinery - it needs its
# own session factory. Kept as a module-level swap point (like
# CONNECTOR_FACTORIES) so tests can point it at an in-memory test engine.
SESSION_FACTORY = SessionLocal


def create_collection_run(
    db: Session, payload: CollectionParamsRequest
) -> tuple[str, state_store.CollectionState]:
    """Persists the initial DB row and in-memory progress state. Does not start the run."""
    sources = [source.value for source in payload.sources]
    run = CollectionRun(keywords=payload.keywords, sources=sources, status=CollectionStatus.RUNNING)
    db.add(run)
    db.commit()
    db.refresh(run)

    collection_id = run.public_id
    state = state_store.create_state(collection_id, keywords=payload.keywords, sources=sources)
    return collection_id, state


async def run_collection_in_background(collection_id: str, payload: CollectionParamsRequest) -> None:
    state = state_store.get_state(collection_id)
    if state is None:  # pragma: no cover - defensive, state is always created just before this runs
        return

    filters = SearchFilters(year_from=payload.year_from, year_to=payload.year_to)

    try:
        articles = await run_collection(
            state,
            connector_factories=CONNECTOR_FACTORIES,
            max_articles_per_keyword=payload.max_articles_per_keyword,
            filters=filters,
        )
    except Exception as exc:
        logger.exception("collection_crashed", extra={"collection_id": collection_id})
        state.status = CollectionStatus.FAILED
        state.error = str(exc)
        state.mark_finished()
        _persist_final_state(collection_id, state, article_count=0)
        return

    if state.abort_requested:
        state.status = CollectionStatus.FAILED
        state.error = state.error or "Collection aborted by user."
    elif any(source.status == "failed" for source in state.source_progress.values()):
        state.status = CollectionStatus.WARNING
        state.warning = state.warning or "One or more sources failed; results may be incomplete."
    else:
        state.status = CollectionStatus.COMPLETED

    state.mark_finished()
    _persist_final_state(collection_id, state, article_count=len(articles))


def _persist_final_state(collection_id: str, state: state_store.CollectionState, *, article_count: int) -> None:
    db = SESSION_FACTORY()
    try:
        run = db.get(CollectionRun, _numeric_id(collection_id))
        if run is not None:
            run.status = state.status
            run.article_count = article_count
            db.commit()
    finally:
        db.close()


def _numeric_id(public_id: str) -> int:
    return int(public_id.removeprefix("COL-"))
