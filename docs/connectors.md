# Scientific Source Connectors

This document tracks each connector's API details, rate limits, and how to verify it against the real (non-mocked) API before merging.

> Need a source that isn't listed below (IEEE Xplore, HAL, DOAJ, CORE, Europe PMC, an
> institutional repository, ...)? See [`docs/custom-connectors.md`](custom-connectors.md) -
> a config-driven **Custom Connector** can add it without writing a new connector file.

## Shared connector infrastructure

All connectors (arXiv, OpenAlex, Crossref, PubMed, Semantic Scholar) are built on the same shared infrastructure rather than reimplementing HTTP/retry/rate-limit logic per source:

| Module | Responsibility |
|---|---|
| `app/connectors/base.py` | `BaseConnector` interface every connector implements (`search(keyword, max_results, filters)`) |
| `app/infra/retries.py` | `call_with_retry()` — resilient HTTP layer (US-03.6). Retries only on 5xx, 429, and network/timeout errors; exponential backoff (100ms → 400ms → 1600ms), max 2 retries. Other 4xx responses (e.g. 404, 400) are returned as-is, never retried, and surfaced by the connector as `ConnectorError` immediately. Every attempt logs duration; persistent failure logs a structured entry and raises `ConnectorError`. |
| `app/orchestrator/rate_limiter.py` | `AsyncRateLimiter` — one shared instance per source (`ARXIV_RATE_LIMITER`, `CROSSREF_RATE_LIMITER`, `OPENALEX_RATE_LIMITER`, `PUBMED_RATE_LIMITER`, `SEMANTIC_SCHOLAR_RATE_LIMITER`), enforcing each source's minimum interval between requests. |
| `app/infra/cache.py` | In-memory, per-process cache of raw connector responses, keyed by `(source, keyword, params)`, TTL from `settings.cache_ttl_hours`. Lets the dedup/cleaning pipeline be re-tuned without re-hitting the API. |
| `app/domain/entities.py` | `RawArticle` (common schema), `SourceEnum`, `ConnectorError(source, endpoint, keyword, error_class, message)` |
| `app/connectors/crossref.py::normalize_doi` | Shared DOI normalization (strip `doi.org` prefix, lowercase, validate `^10\.\d{4,9}/.+$`) — reused as-is by PubMed and Semantic Scholar rather than reimplemented per source. |

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
| **API docs** | https://docs.openalex.org/ |
| **Endpoint** | `https://api.openalex.org/works` (JSON) |
| **Auth** | None required — polite pool via `mailto=` query param (sent on every request) + `User-Agent` header, per Appendix B rule 7 |
| **Rate limit** | 10 req/s (`RATE_LIMIT_OPENALEX_RPS`), via `OPENALEX_RATE_LIMITER` (shared infra) |
| **Domain coverage** | Cross-discipline global index of scientific works |

**Field mapping (per US-03.2's acceptance criteria):**
- `cited_by_count` → `citation_count`.
- `concepts[0].display_name` → `domain` (first/top concept only).
- `title` → `title`, falling back to `display_name` if `title` is absent.
- `doi` → normalized: strips the `https://doi.org/` prefix, lowercased.
- `authorships[].author.display_name` → `authors` (entries with no
  `display_name` are skipped rather than producing a blank author).
- `abstract_inverted_index` → `abstract`: OpenAlex doesn't return plain-text
  abstracts, only an inverted index (`{word: [positions]}`) for copyright
  reasons — `_reconstruct_abstract()` rebuilds the original word order from
  it.
- `id` (OpenAlex's own work URL, e.g. `https://openalex.org/W123...`) →
  `url`.

**Pagination:** cursor-based (`cursor=*` then `meta.next_cursor` from each
response), page size 25 per request (`DEFAULT_PAGE_SIZE`; OpenAlex's own
per-page cap is 200). Stops as soon as `max_results` is reached — never
requests a full page just to discard the extra — and stops cleanly if a
page comes back empty or without a `next_cursor`.

**Resilience:** every request goes through `call_with_retry` (5xx/429
retried with exponential backoff, max 2 retries — see the shared
infrastructure table above) and is cached in-memory per `(keyword,
max_results, year_from, year_to)` for `CACHE_TTL_HOURS`.

**Known quirks:**
- `primary_location` can be a **present-but-`null`** key (not just an
  absent one) when OpenAlex hasn't identified a venue for a work — seen
  live, not just in docs. The naive chained-`.get()` approach crashes on
  this shape; `_map_to_raw_article` checks for `None` explicitly before
  reading `primary_location["source"]["display_name"]`. Regression test:
  `test_openalex.py`.
- Year filtering uses OpenAlex's `filter=from_publication_date:...,to_publication_date:...`
  syntax (full ISO dates, `YYYY-01-01`/`YYYY-12-31`), not a simple
  `year=` param.
- Live-verified against the real API as part of an end-to-end orchestrator
  run (2 keywords × 2 sources including OpenAlex, 20 articles, ~4s — see
  `docs/limitations.md`'s US-03.4 entry).

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

---

## PubMed

| | |
|---|---|
| **Status** | ✅ Implemented |
| **File** | `backend/app/connectors/pubmed.py` |
| **Live check** | `docker compose exec backend python scripts/check_pubmed_live.py` |
| **API docs** | https://www.ncbi.nlm.nih.gov/books/NBK25501/ |
| **Endpoints** | `esearch.fcgi` (keyword → PMIDs, JSON) then `efetch.fcgi` (PMIDs → full records, XML) — E-utilities has no single search+fetch call, so every `search()` makes two requests, each going through the shared rate limiter and resilient HTTP layer independently |
| **Auth** | None required. `tool` + `email` (`settings.polite_pool_email`) sent on every request per NCBI's usage policy. Optional `PUBMED_API_KEY` raises the allowed rate from 3 req/s to 10 req/s. |
| **Rate limit** | 3 req/s without a key (`RATE_LIMIT_PUBMED_RPS`), via `PUBMED_RATE_LIMITER` (shared infra) |
| **Domain coverage** | Biomedical / life sciences literature |

**Known quirks:**
- If `esearch` returns zero PMIDs for a keyword, `efetch` is skipped entirely (no point fetching nothing) and an empty list is cached/returned rather than treated as an error.
- Author entries can be a person (`ForeName` + `LastName`) or a `CollectiveName` (e.g. a study group/consortium) — both are handled; `CollectiveName` is used as-is when present.
- Year comes from `PubDate/Year`, but some records only carry a free-text `MedlineDate` (e.g. `"2019 Jan-Feb"`) — the connector falls back to parsing the leading 4 digits.
- DOI can appear in `PubmedData/ArticleIdList/ArticleId[@IdType='doi']` or (less reliably) `Article/ELocationID[@EIdType='doi']`; the connector checks the former first, then normalizes via the shared `normalize_doi` (imported from `crossref.py`).
- Not every PubMed record has an abstract (e.g. some older or non-original-research entries) — emitted with `abstract = None` rather than dropped, consistent with the other connectors.

---

## Semantic Scholar

| | |
|---|---|
| **Status** | ✅ Implemented |
| **File** | `backend/app/connectors/semantic_scholar.py` |
| **Live check** | `docker compose exec backend python scripts/check_semantic_scholar_live.py` |
| **API docs** | https://api.semanticscholar.org/api-docs/graph |
| **Endpoint** | `https://api.semanticscholar.org/graph/v1/paper/search` (JSON) |
| **Auth** | None required — unauthenticated requests share a low-throughput public pool. Optional `SEMANTIC_SCHOLAR_API_KEY` is sent as the `x-api-key` header for a faster tier. |
| **Rate limit** | Conservative default of 1 req/s (`RATE_LIMIT_SEMANTIC_SCHOLAR_RPS`) for the unauthenticated pool, via `SEMANTIC_SCHOLAR_RATE_LIMITER` (shared infra) |
| **Domain coverage** | Cross-discipline (AI-powered index spanning all fields of research) |

**Known quirks:**
- The Graph API's `limit` parameter caps at 100 regardless of what's requested — `max_results > 100` is silently clamped to 100 (the orchestrator's own compliance cap, US-03.7, already keeps `max_articles_per_keyword <= 100`, so this is a backstop, not the primary enforcement).
- `fieldsOfStudy` is a list (e.g. `["Computer Science", "Medicine"]`); the first entry maps to `domain`, and the full list maps to `categories`, matching how arXiv's `categories`/`domain` split works.
- DOI comes from `externalIds.DOI` and is normalized via the shared `normalize_doi` (imported from `crossref.py`).
- Unauthenticated traffic is shared across all Semantic Scholar API users globally, so 429s are more likely here than on the other sources under load — this is exactly why the rate limit defaults conservative rather than matching the documented ceiling.
