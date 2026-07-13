from fastapi import APIRouter

from app.schemas.collections import (
    CollectionParamsRequest,
    CollectionParamsResponse,
    CollectionParamsSummary,
)

router = APIRouter(prefix="/collections", tags=["collections"])

# Rough per-source estimate for the runtime preview. The real orchestrator (US-03.4)
# will replace this with an actual measured figure.
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
