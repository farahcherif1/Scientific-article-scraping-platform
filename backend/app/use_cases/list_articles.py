"""
List/filter/sort (US-04.3, US-05.1, US-05.2) and stats (US-05.3, US-05.4)
read models over the `articles` table persisted by
`app/use_cases/start_collection.py::_persist_articles`.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, nulls_last, select
from sqlalchemy.orm import Session

from app.db.models import Article

_SORT_COLUMNS = {
    "relevance": Article.relevance_score,
    "year": Article.year,
    "citation_count": Article.citation_count,
}


@dataclass
class ArticleFilters:
    year_from: int | None = None
    year_to: int | None = None
    sources: list[str] | None = None
    has_doi: bool | None = None
    has_abstract: bool | None = None
    keyword: str | None = None


@dataclass
class ArticlePage:
    items: list[Article]
    total: int


def _base_query(collection_run_id: int, filters: ArticleFilters, *, exclude_duplicates: bool = True):
    stmt = select(Article).where(Article.collection_run_id == collection_run_id)
    if exclude_duplicates:
        stmt = stmt.where(Article.is_duplicate.is_(False))
    if filters.year_from is not None:
        stmt = stmt.where(Article.year >= filters.year_from)
    if filters.year_to is not None:
        stmt = stmt.where(Article.year <= filters.year_to)
    if filters.sources:
        stmt = stmt.where(Article.source.in_(filters.sources))
    if filters.has_doi is not None:
        stmt = stmt.where(Article.doi.isnot(None) if filters.has_doi else Article.doi.is_(None))
    if filters.has_abstract is not None:
        stmt = stmt.where(
            Article.abstract.isnot(None) if filters.has_abstract else Article.abstract.is_(None)
        )
    if filters.keyword:
        stmt = stmt.where(Article.search_keyword.ilike(f"%{filters.keyword}%"))
    return stmt


def list_articles(
    db: Session,
    collection_run_id: int,
    *,
    page: int,
    page_size: int,
    sort: str,
    filters: ArticleFilters,
) -> ArticlePage:
    stmt = _base_query(collection_run_id, filters)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    descending = sort.startswith("-")
    field = sort.removeprefix("-")
    column = _SORT_COLUMNS.get(field, Article.relevance_score)
    order = column.desc() if descending else column.asc()
    stmt = stmt.order_by(nulls_last(order), Article.id.asc())

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = list(db.scalars(stmt))

    return ArticlePage(items=items, total=total)


def get_articles_for_export(
    db: Session, collection_run_id: int, *, sort: str, filters: ArticleFilters
) -> list[Article]:
    """
    All articles matching `filters` (duplicates included, unlike
    `list_articles`'s default table view) - the full-precision source for
    US-06.1/US-06.2 exports, which split this same set into
    articles/deduped/duplicates rather than paginating it.
    """
    stmt = _base_query(collection_run_id, filters, exclude_duplicates=False)

    descending = sort.startswith("-")
    field = sort.removeprefix("-")
    column = _SORT_COLUMNS.get(field, Article.relevance_score)
    order = column.desc() if descending else column.asc()
    stmt = stmt.order_by(nulls_last(order), Article.id.asc())

    return list(db.scalars(stmt))


@dataclass
class PerSourceStat:
    source: str
    count: int
    pct_with_doi: float
    pct_with_abstract: float
    pct_with_year: float


@dataclass
class CollectionStats:
    total: int
    deduped: int
    duplicates: int
    pct_with_doi: float
    pct_with_abstract: float
    per_source: list[PerSourceStat]
    articles_per_year: list[tuple[int, int]]


def _pct(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 2) if denominator else 0.0


def get_collection_stats(db: Session, collection_run_id: int) -> CollectionStats:
    all_articles = list(
        db.scalars(select(Article).where(Article.collection_run_id == collection_run_id))
    )
    return compute_stats(all_articles)


def compute_stats(all_articles: list[Article]) -> CollectionStats:
    """
    Pure aggregation over an already-fetched article list, shared by
    `get_collection_stats` (whole-run KPIs) and the export use case (US-06.1
    "stats" sheet, scoped to whatever filters were active in the UI).
    """
    deduped_articles = [a for a in all_articles if not a.is_duplicate]

    total = len(all_articles)
    duplicates = total - len(deduped_articles)

    per_source: dict[str, list[Article]] = {}
    for article in deduped_articles:
        per_source.setdefault(article.source, []).append(article)

    per_source_stats = [
        PerSourceStat(
            source=source,
            count=len(items),
            pct_with_doi=_pct(sum(1 for a in items if a.doi), len(items)),
            pct_with_abstract=_pct(sum(1 for a in items if a.abstract), len(items)),
            pct_with_year=_pct(sum(1 for a in items if a.year), len(items)),
        )
        for source, items in sorted(per_source.items())
    ]

    year_counts: dict[int, int] = {}
    for article in deduped_articles:
        if article.year is not None:
            year_counts[article.year] = year_counts.get(article.year, 0) + 1

    return CollectionStats(
        total=total,
        deduped=len(deduped_articles),
        duplicates=duplicates,
        pct_with_doi=_pct(sum(1 for a in deduped_articles if a.doi), len(deduped_articles)),
        pct_with_abstract=_pct(
            sum(1 for a in deduped_articles if a.abstract), len(deduped_articles)
        ),
        per_source=per_source_stats,
        articles_per_year=sorted(year_counts.items()),
    )
