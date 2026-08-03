# Relevance Scoring (US-04.3)

## Formula

For a normalized article and the list of keywords its collection run was
started with:

```
relevance_score = sum over each keyword k in collection.keywords of:
    count of case-insensitive, word-boundary matches of k in (title + " " + abstract)
```

- Matching is case-insensitive (`"AI"` matches `"ai"`).
- Matching is word-boundary (`\bkeyword\b`), so `"AI"` does not match inside
  `"chair"`, and a multi-word keyword like `"machine learning"` only counts
  when that exact phrase appears, not when the two words appear separately.
- Each keyword's occurrences in the title and in the abstract are counted
  independently and summed — a keyword hit in both the title and the
  abstract contributes twice. An article with no abstract only scores
  against its title.
- The score is per-article, computed once when the article is persisted
  (`app/use_cases/start_collection.py`), against the *full* keyword list the
  collection was run with — not just the single keyword that happened to
  retrieve that article from its source — so articles that also match the
  collection's other search terms rank higher.

Implementation: `app/domain/ranking.py::compute_relevance_score`.

## Sorting

`GET /api/v1/collections/{id}/articles?sort=...` accepts `relevance`,
`year`, or `citation_count`, each optionally prefixed with `-` for
descending order (default: `-relevance`, highest score first). Articles
with a `null` value for the chosen sort field (e.g. missing `year` or
`citation_count`) always sort last, regardless of direction.

## Known limitation

This is a simple keyword-frequency heuristic, not a TF-IDF or embedding-based
ranking — it does not account for term rarity, article length, or semantic
similarity. Logged in `docs/limitations.md`.
