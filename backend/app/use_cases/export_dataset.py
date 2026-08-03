"""
Export use case (US-06.1 xlsx, US-06.2 csv/json). Assembles the same
filtered/sorted article set the Results page is showing (US-05.2) into the
shapes the three exporters need, so "active filters in the UI are reflected
in the exported dataset" holds for every format.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Article, CollectionRun
from app.use_cases.list_articles import (
    ArticleFilters,
    CollectionStats,
    compute_stats,
    get_articles_for_export,
)


@dataclass
class ExportDataset:
    run: CollectionRun
    sort: str
    filters: ArticleFilters
    articles: list[Article]
    deduped: list[Article]
    duplicates: list[Article]
    stats: CollectionStats


def build_export_dataset(
    db: Session, run: CollectionRun, *, sort: str, filters: ArticleFilters
) -> ExportDataset:
    articles = get_articles_for_export(db, run.id, sort=sort, filters=filters)
    deduped = [a for a in articles if not a.is_duplicate]
    duplicates = [a for a in articles if a.is_duplicate]
    return ExportDataset(
        run=run,
        sort=sort,
        filters=filters,
        articles=articles,
        deduped=deduped,
        duplicates=duplicates,
        stats=compute_stats(articles),
    )


def export_params_record(dataset: ExportDataset) -> dict[str, Any]:
    """Flat key/value record documenting the run + the active filters, for the params sheet/context."""
    run = dataset.run
    filters = dataset.filters
    return {
        "collection_id": run.public_id,
        "keywords": "; ".join(run.keywords),
        "sources": "; ".join(run.sources),
        "status": run.status,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "article_count": run.article_count,
        "duplicate_count": run.duplicate_count,
        "sort": dataset.sort,
        "filter_year_from": filters.year_from,
        "filter_year_to": filters.year_to,
        "filter_source": "; ".join(filters.sources) if filters.sources else None,
        "filter_has_doi": filters.has_doi,
        "filter_has_abstract": filters.has_abstract,
        "filter_keyword": filters.keyword,
    }
