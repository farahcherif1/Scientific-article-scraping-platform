# Export Knowledge Graph JSON

Download a graph-ready JSON file from the Results page with **Graph JSON**, or call:

```
GET /api/v1/collections/{collection_id}/export?format=graph
```

The export applies exactly the current article sort and filters (`year_from`,
`year_to`, `source`, `has_doi`, `has_abstract`, and `keyword`). The response is
`application/json` and is named `{collection_id}_knowledge_graph.json`.

## Interactive 3D view

Choose **View 3D Graph** on the Results page to explore the graph directly in
the application. Drag to rotate the 3D projection, use the mouse wheel to
zoom, click a node to inspect it, and toggle node types in the side panel. The
view reads the same graph JSON structure as the downloadable export.

## JSON structure

```json
{
  "format": "knowledge-graph",
  "version": "1.0",
  "collection_id": "COL-0001",
  "generated_at": "2026-08-19T12:00:00+00:00",
  "nodes": [
    {"id": "article:42", "type": "article", "label": "Paper title", "year": 2024},
    {"id": "author:ada%20lovelace", "type": "author", "label": "Ada Lovelace"},
    {"id": "keyword:knowledge%20graph", "type": "keyword", "label": "Knowledge Graph"},
    {"id": "year:2024", "type": "year", "label": "2024", "value": 2024}
  ],
  "links": [
    {"id": "article:42--AUTHORED_BY--author:ada%20lovelace", "source": "article:42", "target": "author:ada%20lovelace", "type": "AUTHORED_BY"},
    {"id": "article:42--HAS_KEYWORD--keyword:knowledge%20graph", "source": "article:42", "target": "keyword:knowledge%20graph", "type": "HAS_KEYWORD"},
    {"id": "article:42--PUBLISHED_IN--year:2024", "source": "article:42", "target": "year:2024", "type": "PUBLISHED_IN"}
  ]
}
```

`nodes` contains one node per article and one shared node for each distinct
author, keyword, and publication year. Article nodes retain useful metadata:
`year`, `doi`, `url`, `venue`, `source`, `citation_count`, and `is_duplicate`.
Keywords combine source-provided `keywords` and extracted `keywords_auto`.

Every item in `links` has an `id`, `source`, `target`, and relationship `type`.
The current relationship directions are article → author (`AUTHORED_BY`),
article → keyword (`HAS_KEYWORD`), and article → year (`PUBLISHED_IN`). IDs are
namespaced and normalised (case-insensitive, URL-safe) so shared entities can
be matched reliably; use `label` for display text in a 3D visualisation.
