# Architecture

Team08-E26 · Yonnov'IA — intelligent scientific-article scraping platform.

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python 3.11+, async), Pydantic v2 + pydantic-settings |
| Persistence | SQLAlchemy 2.0 ORM, SQLite (MVP) — see [Roadmap](#roadmap-notes) for Postgres |
| Outbound HTTP | httpx (async), tenacity (retry/backoff) |
| Domain algorithms | rapidfuzz (fuzzy title matching), scikit-learn (TF-IDF keyword extraction) |
| Exports | stdlib `csv`, `openpyxl` (no pandas) |
| Frontend | React 18 + Vite + TypeScript, React Router, Tailwind CSS |
| Frontend tests | Vitest + React Testing Library |
| Backend tests | pytest, pytest-asyncio, pytest-httpx (mocked HTTP) |
| CI | GitHub Actions (`.github/workflows/ci.yml`) — lint + test both stacks on every PR to `main`/`develop` |
| Local dev / deploy | Docker Compose (`docker-compose.yml`), one container per service |

## Clean Architecture — 4 layers, one direction

```
   api  ──────▶  use_cases  ──────▶  domain  ◀──────  connectors / db / infra
(FastAPI          (orchestration,      (pure,           (I/O: HTTP clients,
 routers,          no I/O of its        zero-I/O          SQLAlchemy models/
 Pydantic          own beyond what      business          session, JSON
 request/response  it calls)           rules, unit-       logging, retry/
 schemas)                              testable with      rate-limit infra)
                                        no network/DB)
```

`domain/` never imports from `api/`, `connectors/`, or `db/` — it is pure
Python operating on plain dataclasses/Pydantic models
(`app/domain/entities.py`), which is what makes it unit-testable without a
network connection or a database. Everything that touches the outside world
(HTTP calls, the DB session, structured logging) lives in `connectors/`,
`db/`, or `infra/`, and is wired together by `use_cases/`, which `api/`
calls as a thin adapter layer.

```
backend/app/
├── api/v1/            FastAPI routers — one file per resource, thin: parse
│                       request → call a use case → shape the response.
│                       keywords.py, collections.py, articles.py, exports.py,
│                       history.py, custom_connectors.py
├── schemas/            Pydantic request/response models (one file per
│                       resource, mirrors api/v1/)
├── use_cases/           Orchestration: wires api → domain/connectors/db.
│                       start_collection.py, list_articles.py,
│                       export_dataset.py, list_collection_history.py,
│                       manage_custom_connectors.py
├── domain/             Pure business logic, zero I/O:
│                       cleaning.py       — keyword + metadata normalization
│                       deduplication.py  — cross-source duplicate detection
│                       compliance.py     — max-articles-per-keyword cap
│                       ranking.py        — relevance scoring
│                       enrichment.py     — TF-IDF auto-keyword extraction
│                       entities.py       — RawArticle / ArticleClean / errors
├── connectors/          One file per scientific source, all implementing
│                       BaseConnector.search(keyword, max_results, filters):
│                       arxiv.py, openalex.py, crossref.py, pubmed.py,
│                       semantic_scholar.py, generic.py (config-driven
│                       "Custom Connector" — see custom-connectors.md),
│                       registry.py (merges built-in + custom factories)
├── orchestrator/        runner.py   — keyword×source fan-out (asyncio.gather
│                       across sources, sequential per source)
│                       rate_limiter.py — one shared AsyncRateLimiter per
│                       source, so concurrent collections don't multiply the
│                       effective request rate
│                       state.py    — in-memory progress store for
│                       GET /collections/{id}/progress polling
├── infra/               retries.py  — call_with_retry(): shared resilient
│                       HTTP layer (exp. backoff, max 2 retries, 5xx/429 only)
│                       cache.py    — in-memory per-process response cache
│                       logging.py  — JSON log formatter
├── db/                  models.py (SQLAlchemy ORM), session.py (engine +
│                       get_db() dependency), indexes.py
├── exporters/            csv_exporter.py, xlsx_exporter.py, json_exporter.py,
│                       common.py (shared field mapping + formula-injection
│                       sanitization)
├── config.py            Settings (pydantic-settings, reads backend/.env)
└── main.py               FastAPI app, CORS, router registration, /health
```

Frontend mirrors the same "thin page, dumb API client" split:

```
frontend/src/
├── pages/       One component per route (KeywordsPage, ConfigurePage,
│                CollectionPage, ResultsPage, HistoryPage, SourcesPage,
│                CustomConnectorWizardPage) — see App.tsx for the router.
├── api/         One fetch-wrapper module per backend resource
│                (keywords.ts, collections.ts, articles.ts, history.ts,
│                customConnectors.ts) — the only place that knows about
│                VITE_API_BASE_URL and response shapes.
├── components/   Shared UI (TopNav, Select, Toggle, ArticlesPerYearChart,
│                ColumnMappingDialog).
└── lib/          Pure helpers (jsonPathSuggest.ts — client-side dot-path
                 suggestion for the custom-connector wizard).
```

## Request flow: a full collection run

1. **Keywords** (`/keywords`, US-02.1) — the user pastes or uploads (Excel)
   a keyword list. `POST /api/v1/keywords/parse` (or the Excel
   preview/extract endpoints) cleans and case-insensitively dedupes it
   (`app/domain/cleaning.py::split_raw_keyword_string` /
   `clean_keywords`) — but the actual parsing shown live in the UI is done
   client-side (`frontend/src/api/keywords.ts`); the backend endpoint
   mirrors the same logic for the Excel-import path and is unit-tested
   against the same cases.
2. **Configure** (`/collections/new`) — pick sources (5 built-in +
   any enabled custom connectors), a per-keyword article cap (10–100,
   hard-capped at 100 — see `docs/collection-charter.md`), and an optional
   year range.
3. **Start** — `POST /api/v1/collections` validates the payload
   (`CollectionParamsRequest`, `app/schemas/collections.py`), persists a
   `CollectionRun` row (`status=running`), creates an in-memory
   `CollectionState` (`app/orchestrator/state.py`), and hands the actual
   work to a FastAPI `BackgroundTask` (`run_collection_in_background`) so
   the request returns `202` immediately with the run's id.
4. **Fan-out** (`app/orchestrator/runner.py::run_collection`) — every
   selected source runs concurrently (`asyncio.gather`); within one
   source, keywords run sequentially against that source's shared
   `AsyncRateLimiter`. One source failing (`ConnectorError`, raised after
   `app/infra/retries.py`'s retries are exhausted) is logged and marks
   that source `failed` — it never blocks or crashes the others. The
   in-memory `CollectionState` is mutated as it goes, which is what
   `GET /collections/{id}/progress` (polled by `CollectionPage`) reads.
5. **Compliance cap** — `app/domain/compliance.py::enforce_max_articles_per_keyword`
   truncates any (source, keyword) group that over-fetched, as a backstop
   (every connector already stops itself at `max_results`).
6. **Normalize** (`app/domain/cleaning.py::normalize_articles`, US-04.1) —
   every `RawArticle` becomes an `ArticleClean`: titles/abstracts stripped
   of HTML/LaTeX markup, author names reshaped to a consistent "First
   Last" form, years/DOIs normalized. Nothing is dropped for a missing
   field — it's set to `null` and listed in `missing_fields`.
7. **Deduplicate** (`app/domain/deduplication.py::deduplicate_articles`,
   US-04.2) — DOI-exact matches first, then rapidfuzz title similarity
   (≥ 92, same year) or exact-title-with-similar-authors as a fallback.
   Duplicates are **flagged, never deleted**
   (`is_duplicate`/`duplicate_group_id`/`duplicate_similarity_score`/
   `duplicate_rule`), per the Collection Charter.
8. **Persist** (`use_cases/start_collection.py::_persist_articles`) — one
   `Article` row per `ArticleClean`, plus a computed `relevance_score`
   (`app/domain/ranking.py`, see `docs/relevance.md`) and auto-extracted
   `keywords_auto` (`app/domain/enrichment.py`, TF-IDF over the abstract).
9. **Results** (`/collections/{id}`, US-04.3/05.1–05.4) —
   `GET /collections/{id}/articles` (pagination, sort, AND-combined
   filters) and `GET /collections/{id}/stats` (KPIs, per-source quality,
   per-year counts) back the dashboard; filter state round-trips through
   the URL so a filtered view is shareable.
10. **Export** (`/collections/{id}/export`, US-06.1/06.2) — the exact
    filtered/sorted set the Results page is showing, as `.xlsx` (5 sheets:
    articles/deduped/duplicates/stats/params), `.csv`, or `.json`.

## Custom connectors — the one config-driven exception

`app/connectors/generic.py::GenericConnector` implements the same
`BaseConnector` contract as the 5 built-ins, but is driven entirely by a
JSON config (`CustomConnectorConfig`) a researcher fills in through a
wizard rather than a new Python file — see `docs/custom-connectors.md` for
the full design, including the SSRF guard required because `base_url` is
entirely user-supplied. `app/connectors/registry.py` merges enabled custom
connectors' factories with the 5 built-in ones into one dict; the
orchestrator (step 4 above) doesn't know or care which kind it's calling.

## API conventions

- Every endpoint lives under `/api/v1/*`.
- Error responses: `{"error": {"code": "...", "message": "..."}}` (FastAPI's
  default `{"detail": ...}` shape appears for framework-level validation
  errors — see `docs/data-dictionary.md`).
- Listing endpoints return the envelope
  `{"data": [...], "pagination": {...}, "sort": "...", "filters": {...}}`.
- No authentication on any endpoint — see "Auth model" in
  `docs/security-review.md` and `docs/limitations.md` for why, and what
  that implies operationally.

## Roadmap notes

- **SQLite → PostgreSQL 16.** Currently every table is created via
  `Base.metadata.create_all()` (`app/db/session.py::init_db`) — there is no
  Alembic migration yet for any table, despite Alembic being a declared
  dependency. Fine for the single-process SQLite MVP; a real migration
  history is needed before the Postgres cutover.
- **In-memory state, single process.** `app/orchestrator/state.py` (run
  progress) and `app/infra/cache.py` (connector response cache) are both
  per-process Python dicts — not shared across workers, lost on restart.
  Revisit alongside the Postgres move if the deployment ever becomes
  multi-worker.
- See `docs/limitations.md` for the full, itemized list of known scope
  limits per story, and `docs/security-review.md` for the latest security
  pass's findings and what's intentionally deferred.
