from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.orchestrator import state as state_store
from app.schemas.collections import (
    CollectionParamsRequest,
    CollectionParamsResponse,
    CollectionParamsSummary,
    CollectionProgressResponse,
    SourceProgressItem,
    StartCollectionResponse,
)
from app.use_cases.start_collection import create_collection_run, run_collection_in_background

router = APIRouter(prefix="/collections", tags=["collections"])

# Rough per-source estimate for the runtime preview shown before a run starts.
ESTIMATED_SECONDS_PER_SOURCE = 15


@router.post("/params/validate", response_model=CollectionParamsResponse)
def validate_params(payload: CollectionParamsRequest) -> CollectionParamsResponse:
    summary = CollectionParamsSummary(
        selected_keywords=len(payload.keywords),
        active_sources=len(payload.sources),
        max_potential_yield=(
            payload.max_articles_per_keyword * len(payload.keywords) * len(payload.sources)
        ),
        estimated_runtime_seconds=ESTIMATED_SECONDS_PER_SOURCE * len(payload.sources),
    )
    return CollectionParamsResponse(valid=True, summary=summary)


@router.post("", response_model=StartCollectionResponse, status_code=202)
def start_collection(
    payload: CollectionParamsRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> StartCollectionResponse:
    # Security review finding: this endpoint has no auth and no other
    # throttle, so nothing previously stopped a client from starting
    # unboundedly many concurrent collections - each its own keyword x source
    # fan-out against real third-party APIs (resource exhaustion here, and a
    # compliance-charter rate-limit risk there). 429 is the standard "you're
    # sending requests too fast, retry later" response for this.
    if state_store.count_running() >= state_store.MAX_CONCURRENT_RUNNING:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many collections are already running "
                f"(max {state_store.MAX_CONCURRENT_RUNNING} concurrent). Try again shortly."
            ),
        )
    collection_id, state = create_collection_run(db, payload)
    background_tasks.add_task(run_collection_in_background, collection_id, payload)
    return StartCollectionResponse(id=collection_id, status=state.status)


@router.get("/{collection_id}/progress", response_model=CollectionProgressResponse)
def get_progress(collection_id: str) -> CollectionProgressResponse:
    state = state_store.get_state(collection_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Unknown collection id.")
    return CollectionProgressResponse(
        id=state.id,
        status=state.status,
        overall_progress=state.overall_progress,
        current_keyword=state.current_keyword,
        elapsed_seconds=state.elapsed_seconds,
        sources=[
            SourceProgressItem(
                source=source.source,
                status=source.status,
                detail=source.detail,
                articles_fetched=source.articles_fetched,
            )
            for source in state.source_progress.values()
        ],
        warning=state.warning,
        error=state.error,
    )


@router.post("/{collection_id}/abort", status_code=204)
def abort_collection(collection_id: str) -> None:
    state = state_store.get_state(collection_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Unknown collection id.")
    state.abort_requested = True
