"""
JSON export (US-06.2). Produces a JSON array of article records matching
the app's canonical article schema (ArticleItem / Appendix A) - list
fields (authors, categories, missing_fields) stay real JSON arrays here,
unlike the flattened CSV/XLSX cells.
"""
from __future__ import annotations

import json

from app.db.models import Article
from app.exporters.common import article_to_record


def export_articles_to_json(articles: list[Article]) -> str:
    records = []
    for article in articles:
        record = article_to_record(article)
        record["collection_date"] = (
            record["collection_date"].isoformat() if record["collection_date"] else None
        )
        records.append(record)
    return json.dumps(records, indent=2, ensure_ascii=False)
