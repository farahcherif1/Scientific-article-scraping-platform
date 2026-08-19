"""Knowledge-graph JSON exporter for article collections.

The compact ``nodes``/``links`` shape is directly consumable by common graph
and 3D graph viewers.  Entity IDs are namespaced and stable within a
collection, which also makes them safe to merge in downstream tooling.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from urllib.parse import quote

from app.db.models import Article


def _entity_id(kind: str, value: str | int) -> str:
    """Create a namespaced, URL-safe ID without relying on display labels."""
    normalized = " ".join(str(value).split()).casefold()
    return f"{kind}:{quote(normalized, safe='')}"


def _unique_terms(values: Iterable[str]) -> list[str]:
    """Remove empty and duplicate terms while retaining their first spelling."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        label = " ".join(value.split())
        key = label.casefold()
        if label and key not in seen:
            result.append(label)
            seen.add(key)
    return result


def export_articles_to_graph_json(articles: list[Article], collection_id: str) -> str:
    """Return articles plus author, keyword, and year entities as a graph JSON."""
    nodes: list[dict] = []
    links: list[dict] = []
    node_ids: set[str] = set()

    def add_node(node_id: str, node_type: str, label: str, **properties: object) -> None:
        if node_id not in node_ids:
            nodes.append({"id": node_id, "type": node_type, "label": label, **properties})
            node_ids.add(node_id)

    def add_link(source: str, target: str, link_type: str) -> None:
        links.append(
            {
                "id": f"{source}--{link_type}--{target}",
                "source": source,
                "target": target,
                "type": link_type,
            }
        )

    for article in articles:
        article_id = f"article:{article.id}"
        add_node(
            article_id,
            "article",
            article.title,
            year=article.year,
            doi=article.doi,
            url=article.url,
            venue=article.venue,
            source=article.source,
            citation_count=article.citation_count,
            is_duplicate=article.is_duplicate,
        )

        for author in _unique_terms(article.authors):
            author_id = _entity_id("author", author)
            add_node(author_id, "author", author)
            add_link(article_id, author_id, "AUTHORED_BY")

        # Both connector-provided and automatically extracted keywords are
        # useful graph concepts.  Duplicates across the two lists collapse.
        for keyword in _unique_terms([*(article.keywords or []), *(article.keywords_auto or [])]):
            keyword_id = _entity_id("keyword", keyword)
            add_node(keyword_id, "keyword", keyword)
            add_link(article_id, keyword_id, "HAS_KEYWORD")

        if article.year is not None:
            year_id = f"year:{article.year}"
            add_node(year_id, "year", str(article.year), value=article.year)
            add_link(article_id, year_id, "PUBLISHED_IN")

    payload = {
        "format": "knowledge-graph",
        "version": "1.0",
        "collection_id": collection_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "nodes": nodes,
        "links": links,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
