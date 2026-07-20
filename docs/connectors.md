# Scientific Source Connectors

This document tracks each connector's API details, rate limits, and how to verify it against the real (non-mocked) API before merging.

## Shared connector infrastructure

All connectors (arXiv, OpenAlex, Crossref) are built on the same shared infrastructure rather than reimplementing HTTP/retry/rate-limit logic per source:

| Module | Responsibility |
|---|---|
| `app/connectors/base.py` | `BaseConnector` interface every connector implements (`search(keyword, max_results, filters)`) |
| `app/infra/retries.py` | `call_with_retry()` — resilient HTTP layer (US-03.6). Retries only on 5xx, 429, and network/timeout errors; exponential backoff (100ms → 400ms → 1600ms), max 2 retries. Other 4xx responses (e.g. 404, 400) are returned as-is, never retried, and surfaced by the connector as `ConnectorError` immediately. Every attempt logs duration; persistent failure logs a structured entry and raises `ConnectorError`. |
| `app/orchestrator/rate_limiter.py` | `AsyncRateLimiter` — one shared instance per source (`ARXIV_RATE_LIMITER`, `CROSSREF_RATE_LIMITER`, `OPENALEX_RATE_LIMITER`, `PUBMED_RATE_LIMITER`), enforcing each source's minimum interval between requests. |
| `app/infra/cache.py` | In-memory, per-process cache of raw connector responses, keyed by `(source, keyword, params)`, TTL from `settings.cache_ttl_hours`. Lets the dedup/cleaning pipeline be re-tuned without re-hitting the API. |
| `app/domain/entities.py` | `RawArticle` (common schema), `SourceEnum`, `ConnectorError(source, endpoint, keyword, error_class, message)` |

## Verifying a connector against the real API

Unit tests mock all HTTP calls (via `pytest-httpx`), which is correct for CI - fast, deterministic, no external dependency. But mocks can't catch real-world drift (endpoint changes, redirect behavior, schema changes on the provider's side).

Before merging any connector PR, run its live sanity-check script once manually:

```bash
docker compose exec backend python scripts/check_<source>_live.py
```

This prints real records fetched from the actual API so you can eyeball that titles, authors, years, abstracts, and source-specific fields (categories, DOIs, etc.) look correct. It's not part of the automated test suite - it's a manual pre-merge check, similar to a smoke test.

If a live check ever fails where the mocked tests pass, that's a signal the provider changed something (a moved endpoint, a redirect, a schema change) that our mocks are still blind to - worth investigating before merging, since users would hit the same failure in production.

---

## arXiv

| | |
|---|---|
| **Status** | ✅ Implemented (US-03.1) |
| **File** | `backend/app/connectors/arxiv.py` |
| **Live check** | `docker compose exec backend python scripts/check_arxiv_live.py` |
| **API docs** | https://arxiv.org/help/api/user-manual |
| **Endpoint** | `https://export.arxiv.org/api/query` (Atom/XML) |
| **Auth** | None |
| **Rate limit** | ~1 request / 3 seconds, via `ARXIV_RATE_LIMITER` (shared infra) |
| **Domain coverage** | AI, CS, Math, Physics |

**Known quirks:**
- The `http://` variant of the endpoint 301-redirects to `https://`. The connector uses `https://` directly and also sets `follow_redirects=True` on the client as a safety net.
- `primary_category` lives in the arXiv-specific XML namespace (`http://arxiv.org/schemas/atom`), separate from the standard Atom namespace used for `title`, `author`, `summary`, etc. Both namespaces are parsed explicitly (`ATOM_NS` / `ARXIV_NS` constants).
- Some entries may lack `primary_category` — code degrades gracefully to `domain = None` rather than raising.

---

## OpenAlex

| | |
|---|---|
| **Status** | ✅ Implemented (US-03.2, owned by Ilyes) |
| **File** | `backend/app/connectors/openalex.py` |
| **Rate limit** | Via `OPENALEX_RATE_LIMITER` (shared infra) |

*(Details to be filled in by connector owner — see US-03.2.)*

---

## Crossref

| | |
|---|---|
| **Status** | ✅ Implemented (US-03.3) |
| **File** | `backend/app/connectors/crossref.py` |
| **Live check** | `docker compose exec backend python scripts/check_crossref_live.py` |
| **API docs** | https://api.crossref.org/swagger-ui/index.html |
| **Endpoint** | `https://api.crossref.org/works` (JSON) |
| **Auth** | None (polite pool via `mailto=` param + `User-Agent` header, sent on every request) |
| **Rate limit** | 50 req/s (polite pool) per §3.1, via `CROSSREF_RATE_LIMITER` (shared infra) |

**Known quirks:**
- **Abstracts are rarely present.** Crossref's index is metadata-first; most records return no abstract at all. This is expected, not a bug — records are still emitted (never dropped) with `abstract = None`, flagged downstream by the data-quality report (US-04.4).
- **Author lists can be empty**, particularly for edited volumes, reference works, or some book chapters (confirmed against live data — e.g. an MIT Press "Large Language Models" reference entry returned zero authors). The connector emits the record anyway rather than discarding it.
- **Abstracts, when present, may be wrapped in JATS XML tags** (e.g. `<jats:p>...</jats:p>`, `<jats:italic>...</jats:italic>`). Stripped via `_strip_jats_tags()` before mapping.
- **DOI normalization**: strips the `https://doi.org/` (or `http://dx.doi.org/`) prefix and lowercases, then validates against `^10\.\d{4,9}/.+$`. Verified against live data at 100% DOI coverage on a sample query, well above the 80% acceptance threshold.
- **`document_type`** (e.g. `"journal-article"`, `"proceedings-article"`) is present in Crossref's raw response but is currently **not persisted** — `RawArticle` has no `document_type` field. This is an explicit deliverable in Tâche 3.3 ("Extraction type de document") that is presently descoped; flag with whoever owns `app/domain/entities.py` if/when it needs to be added back.
