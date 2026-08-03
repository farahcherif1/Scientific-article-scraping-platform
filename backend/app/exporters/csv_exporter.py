"""
CSV export (US-06.2). Built with the stdlib `csv` module: UTF-8 with a BOM
(Excel needs the BOM to detect UTF-8 rather than guessing a local codepage),
comma-separated, and every string field quoted (numeric fields left bare)
via QUOTE_NONNUMERIC.
"""
from __future__ import annotations

import csv
import io

from app.db.models import Article
from app.exporters.common import ARTICLE_FIELDS, article_to_flat_row


def export_articles_to_csv(articles: list[Article]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=ARTICLE_FIELDS, quoting=csv.QUOTE_NONNUMERIC)
    writer.writeheader()
    for article in articles:
        row = article_to_flat_row(article)
        # QUOTE_NONNUMERIC quotes anything that isn't already int/float, so a
        # bare `None` (a missing year, DOI, etc.) is normalized to "" first -
        # otherwise it would print as the bareword `None` instead of a blank cell.
        writer.writerow({key: ("" if value is None else value) for key, value in row.items()})
    return buffer.getvalue().encode("utf-8-sig")
