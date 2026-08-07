from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models import CollectionRun
from app.db.session import get_db
from app.schemas.articles import (
    ArticleItem,
    ArticlesPagination,
    ArticlesResponse,
    CollectionStatsResponse,
    PerSourceStat,
    SortField,
    YearCount,
)
from app.use_cases.list_articles import ArticleFilters, get_collection_stats, list_articles

router = APIRouter(prefix="/collections/{collection_id}", tags=["articles"])


def _get_run_or_404(db: Session, collection_id: str) -> CollectionRun:
    try:
        numeric_id = CollectionRun.numeric_id(collection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Unknown collection id.") from exc
    run = db.get(CollectionRun, numeric_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown collection id.")
    return run


@router.get("/articles", response_model=ArticlesResponse)
def get_articles(
    collection_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: SortField = "-relevance",
    year_from: int | None = Query(default=None, ge=1900),
    year_to: int | None = Query(default=None, ge=1900),
    source: list[str] | None = Query(default=None),
    has_doi: bool | None = None,
    has_abstract: bool | None = None,
    keyword: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
) -> ArticlesResponse:
    if year_from is not None and year_to is not None and year_from > year_to:
        raise HTTPException(status_code=422, detail="year_from must not be after year_to.")
    if source is not None and len(source) > 50:
        raise HTTPException(status_code=422, detail="Too many source filters.")

    run = _get_run_or_404(db, collection_id)
    filters = ArticleFilters(
        year_from=year_from,
        year_to=year_to,
        sources=source,
        has_doi=has_doi,
        has_abstract=has_abstract,
        keyword=keyword,
    )
    result = list_articles(
        db, run.id, page=page, page_size=page_size, sort=sort, filters=filters
    )
    return ArticlesResponse(
        data=[
            ArticleItem(
                id=a.id,
                title=a.title,
                authors=a.authors,
                year=a.year,
                abstract=a.abstract,
                url=a.url,
                doi=a.doi,
                venue=a.venue,
                domain=a.domain,
                categories=a.categories,
                citation_count=a.citation_count,
                keywords=a.keywords,
                keywords_auto=a.keywords_auto,
                source=a.source,
                search_keyword=a.search_keyword,
                collection_date=a.collection_date,
                duplicate_group_id=a.duplicate_group_id,
                is_duplicate=a.is_duplicate,
                missing_fields=a.missing_fields,
                relevance_score=a.relevance_score,
                text_unified=" ".join(
                    part for part in [a.title, a.abstract, a.search_keyword] if part
                ),
                abstract_missing=not bool(a.abstract),
            )
            for a in result.items
        ],
        pagination=ArticlesPagination(total=result.total, page=page, page_size=page_size),
        sort=sort,
        filters={
            "year_from": year_from,
            "year_to": year_to,
            "source": ",".join(source) if source else None,
            "has_doi": has_doi,
            "has_abstract": has_abstract,
            "keyword": keyword,
        },
    )


@router.get("/stats", response_model=CollectionStatsResponse)
def get_stats(collection_id: str, db: Session = Depends(get_db)) -> CollectionStatsResponse:
    run = _get_run_or_404(db, collection_id)
    stats = get_collection_stats(db, run.id)
    return CollectionStatsResponse(
        total=stats.total,
        deduped=stats.deduped,
        duplicates=stats.duplicates,
        pct_with_doi=stats.pct_with_doi,
        pct_with_abstract=stats.pct_with_abstract,
        per_source=[
            PerSourceStat(
                source=s.source,
                count=s.count,
                pct_with_doi=s.pct_with_doi,
                pct_with_abstract=s.pct_with_abstract,
                pct_with_year=s.pct_with_year,
            )
            for s in stats.per_source
        ],
        articles_per_year=[YearCount(year=y, count=c) for y, c in stats.articles_per_year],
    )
