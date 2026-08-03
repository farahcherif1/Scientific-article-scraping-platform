from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import CollectionRun
from app.db.session import get_db
from app.orchestrator import state as state_store
from app.schemas.collections import (
    CollectionDetailResponse,
    CollectionParamsRequest,
    CollectionParamsResponse,
    CollectionParamsSummary,
    CollectionProgressResponse,
    CollectionStatsPerSourceItem,
    CollectionStatsResponse,
    SourceProgressItem,
    StartCollectionResponse,
)
from app.use_cases.start_collection import (
    _numeric_id,
    create_collection_run,
    run_collection_in_background,
)

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
    collection_id, state = create_collection_run(db, payload)
    background_tasks.add_task(run_collection_in_background, collection_id, payload)
    return StartCollectionResponse(id=collection_id, status=state.status)


@router.get("/{collection_id}", response_model=CollectionDetailResponse)
def get_collection(collection_id: str, db: Session = Depends(get_db)) -> CollectionDetailResponse:
    run = db.get(CollectionRun, _numeric_id(collection_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown collection id.")
    return CollectionDetailResponse(
        id=run.public_id,
        keywords=run.keywords,
        sources=run.sources,
        article_count=run.article_count,
        duplicate_count=run.duplicate_count,
        quality_report=run.quality_report,
        created_at=run.created_at,
        status=run.status,
    )


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


@router.get("/{collection_id}/stats", response_model=CollectionStatsResponse)
def get_collection_stats(collection_id: str, db: Session = Depends(get_db)) -> CollectionStatsResponse:
    run = db.get(CollectionRun, _numeric_id(collection_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown collection id.")

    stats_payload = run.stats or {}
    if not stats_payload:
        total = int(run.article_count)
        deduped = max(total - int(run.duplicate_count), 0)
        return CollectionStatsResponse(
            total=total,
            deduped=deduped,
            duplicates=int(run.duplicate_count),
            doi_percentage=0.0,
            abstract_percentage=0.0,
            per_source_counts=[],
            articles_per_year=[],
        )

    return CollectionStatsResponse(
        total=int(stats_payload.get("total", run.article_count)),
        deduped=int(stats_payload.get("deduped", max(run.article_count - run.duplicate_count, 0))),
        duplicates=int(stats_payload.get("duplicates", run.duplicate_count)),
        doi_percentage=float(stats_payload.get("doi_percentage", 0.0)),
        abstract_percentage=float(stats_payload.get("abstract_percentage", 0.0)),
        per_source_counts=[
            CollectionStatsPerSourceItem(**item)
            for item in stats_payload.get("per_source_counts", [])
            if isinstance(item, dict)
        ],
        articles_per_year=[tuple(item) for item in stats_payload.get("articles_per_year", [])],
    )


@router.post("/{collection_id}/abort", status_code=204)
def abort_collection(collection_id: str) -> None:
    state = state_store.get_state(collection_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Unknown collection id.")
    state.abort_requested = True
