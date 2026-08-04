"""
Shared article -> flat-record mapping for the CSV/JSON/XLSX exporters
(US-06.1/US-06.2). One field list/order kept in one place so the three
formats stay in sync.
"""
from __future__ import annotations

from typing import Any

from app.db.models import Article

ARTICLE_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "authors",
    "year",
    "abstract",
    "url",
    "doi",
    "venue",
    "domain",
    "categories",
    "citation_count",
    "source",
    "search_keyword",
    "collection_date",
    "duplicate_group_id",
    "is_duplicate",
    "missing_fields",
    "relevance_score",
    "text_unified",
    "abstract_missing",
)

# Fields that are lists in the ORM/JSON shape but need flattening to a single
# delimited string for the flat, cell-based CSV/XLSX formats. JSON keeps them
# as real arrays (see json_exporter.py).
_LIST_FIELDS = {"authors", "categories", "missing_fields"}


def _build_text_unified(article: Article) -> str:
    parts = [article.title, article.abstract, article.search_keyword]
    return " ".join(part for part in parts if part)


def article_to_record(article: Article) -> dict[str, Any]:
    """The canonical article record (matches `ArticleItem`/Appendix A) as a plain dict."""
    record = {field: getattr(article, field) for field in ARTICLE_FIELDS if field not in {"text_unified", "abstract_missing"}}
    record["text_unified"] = _build_text_unified(article)
    record["abstract_missing"] = not bool(article.abstract)
    return record


def article_to_flat_row(article: Article) -> dict[str, Any]:
    """Same record, with list fields joined for CSV/XLSX cells."""
    record = article_to_record(article)
    for field in _LIST_FIELDS:
        record[field] = "; ".join(record[field])
    if record["collection_date"] is not None:
        record["collection_date"] = record["collection_date"].isoformat()
    return record
