# Known Limitations

- **T-02.5.1 (History endpoint):** `GET /api/v1/history` reads from a new
  `collection_runs` table (`app/db/models.py`). There is no Alembic migration
  for it yet — tables are created via `Base.metadata.create_all()` on startup
  (`app/db/session.py:init_db`). This is fine for the SQLite MVP but should be
  replaced by a proper Alembic migration before the Postgres cutover.
- Clicking a row in `HistoryPage` navigates to `/collections/:id`, which is now
  the real `ResultsPage` (US-05.1, Sprint 5) rather than the earlier
  `Construction`-icon placeholder — see the articles-persistence entry below.
- **US-03.4 (multi-source orchestrator) is implemented and live-tested**
  (`app/orchestrator/runner.py`, `app/orchestrator/state.py`,
  `app/use_cases/start_collection.py`, `POST /api/v1/collections`,
  `GET /api/v1/collections/{id}/progress`, `POST /api/v1/collections/{id}/abort`).
  Verified against the real arXiv + OpenAlex APIs (2 keywords x 2 sources,
  20 articles, ~4s) and end-to-end through a live uvicorn server (async
  `BackgroundTask`, real DB persistence, history reflects the completed run).
  Known scope limits:
  - Progress state lives in an in-memory dict (`app/orchestrator/state.py`),
    same MVP tradeoff as `app/infra/cache.py` — not shared across workers,
    lost on restart. A restart mid-run leaves the `collection_runs` row stuck
    at `status=running` forever (nothing times it out).
  - `SourceId` (schema) and `CONNECTOR_FACTORIES` (orchestrator) now list
    exactly the same three sources (`arxiv`, `openalex`, `crossref`) — every
    schema-valid request is guaranteed to reach a real connector. The
    orchestrator's "unregistered source" handling (fails that source without
    blocking the others) is still there as a safety net for whenever a
    fourth source is added ahead of its connector, and is covered by
    `test_unregistered_source_is_marked_failed_without_blocking_others` in
    `test_orchestrator_runner.py`.
  - Abort is cooperative: `abort_requested` is only checked between keywords,
    not mid-request, so an in-flight HTTP call to a source still completes
    before the abort takes effect.
  - `language`, `domain`, `include_missing_abstract`, and
    `exclude_duplicates_on_export` are accepted by `CollectionParamsRequest`
    but not yet applied anywhere in the fan-out — no connector implements
    language/domain filtering, and the two boolean toggles are export-time
    concerns (US-06.1, Sprint 6) that don't exist yet.
  - `CollectionRun.duplicate_count` is always persisted as `0` — cross-source
    deduplication (US-04.2) doesn't exist yet, so there's nothing to count.
  - Found and fixed live (not caught by prior mocked tests): OpenAlex
    sometimes returns `primary_location: {"source": null}` (key present,
    value null) rather than omitting `primary_location` entirely — the old
    `.get("primary_location", {}).get("source", {})` chain crashed on that
    shape. Fixed in `app/connectors/openalex.py::_map_to_raw_article`, with a
    regression test in `test_openalex.py`.
- **T-03.2 (OpenAlex connector) support code (`app/connectors/base.py`,
  `app/domain/entities.py` additions, `app/infra/retries.py`,
  `app/infra/cache.py`, `app/orchestrator/rate_limiter.py`) was implemented
  to unblock `openalex.py`, which previously couldn't even import.** Notes:
  - `app/infra/cache.py` is an in-memory, per-process dict cache
    (`CACHE_TTL_HOURS`-based TTL). Fine for the single-process SQLite MVP;
    will not survive a restart and won't be shared across workers once we
    move to multiple backend processes — revisit for the Postgres cutover.
  - `app/infra/retries.py` treats HTTP 429 as retryable alongside 5xx/network
    errors (per US-03.2's AC), while all other 4xx responses are returned
    as-is per US-03.6's "never 4xx" rule.
  - `app/orchestrator/rate_limiter.py` defines one limiter instance per
    connector-backed source (OpenAlex/arXiv/CrossRef) from `.env` config.
    A fourth, unimplemented `pubmed` source and a schema-only
    `semantic_scholar` option were removed from the codebase (config,
    rate limiter, `SourceEnum`/`SourceId`, frontend labels) since neither
    had a connector and both were dead surface area. **Both were
    subsequently reintroduced with real connectors** — see the PubMed /
    Semantic Scholar entry below.
  - `app/infra/logging.py` (T-03.6.2) now configures a JSON formatter on the
    root logger via `configure_logging()`, called from `main.py`'s lifespan
    hook, so `retries.py`'s `extra={...}` fields render as JSON.
- **US-03.7 (compliance cap enforcement) is now fully wired into the live
  pipeline.** `app/orchestrator/runner.py::run_collection` calls
  `enforce_max_articles_per_keyword` on the full collected set after fan-out
  and sets `state.warning` if any (source, keyword) group had to be
  truncated (surfaced via `GET /collections/{id}/progress`, which
  `CollectionPage` already renders as a banner). In practice this rarely
  fires today since every connector already stops at `max_results` itself —
  it's a backstop for a connector that over-fetches (covered by
  `test_compliance_cap_is_enforced_even_if_a_connector_over_returns` in
  `test_orchestrator_runner.py`). `max_articles_per_keyword > 100` still
  returns 422 via the Pydantic schema. `ConfigurePage`'s cap notice
  (the "100-article hard cap" panel) is still static copy rather than a
  dynamic warning driven by the actual run — `CollectionPage` is where a
  real capped-run warning would show up, via `progress.warning`.
- **US-04.1 (metadata normalization) is implemented as pure domain functions**
  in `app/domain/cleaning.py` (`normalize_title`, `normalize_authors`,
  `normalize_year`, `normalize_doi`, `normalize_abstract`,
  `normalize_article`/`normalize_articles`, `build_missing_value_report`),
  mapping `RawArticle` -> `ArticleClean` (`app/domain/entities.py`). Covered
  by 38 unit tests in `test_metadata_normalization.py`. **Now wired into the
  pipeline** (`app/use_cases/start_collection.py::run_collection_in_background`
  calls `normalize_articles` then `deduplicate_articles` then persists the
  result) - see the articles-persistence entry below.
- **Article persistence + results API (US-04.3, US-05.1, US-05.2, US-05.3,
  US-05.4) added.** A new `articles` table (`app/db/models.py::Article`)
  stores the normalized, deduplicated output of every completed run,
  written by `app/use_cases/start_collection.py::_persist_articles`
  (duplicates are kept and flagged via `is_duplicate`/`duplicate_group_id`,
  never dropped, per the Collection Charter). `GET
  /api/v1/collections/{id}/articles` (`app/api/v1/articles.py`,
  `app/use_cases/list_articles.py`) supports pagination, `sort=relevance|
  year|citation_count` (optional `-` prefix, default `-relevance`,
  formula in `docs/relevance.md`), and AND-combined filters (`year_from`/
  `year_to` range - articles with no `year` are excluded once either bound
  is set, `source` repeated for a multi-source OR match, `has_doi`,
  `has_abstract`, `keyword` substring on `search_keyword`).
  `GET /api/v1/collections/{id}/stats` returns the KPI
  numbers (total/deduped/duplicates/`%` with DOI/abstract), a per-source
  quality breakdown, and an articles-per-year series for the dashboard
  chart. Known scope limits:
  - Same MVP tradeoff as `collection_runs`/`custom_connectors`: no Alembic
    migration for `articles` yet, just `Base.metadata.create_all()`.
  - The article-listing endpoint's default view excludes duplicates
    (`is_duplicate = false`); there is no "show duplicates in the table"
    toggle yet, only the `duplicates` count on the stats endpoint.
  - `relevance_score` is computed once, at persistence time, against the
    full collection keyword list, and stored on the row (not recomputed
    per request) - a simple keyword-frequency heuristic, not TF-IDF or
    embeddings (see `docs/relevance.md`).
  - `/stats` recomputes per-source and per-year aggregates from the full
    row set on every request - fine at MVP scale, would need caching or
    SQL-side aggregation for a much larger corpus.
- **PubMed and Semantic Scholar connectors are implemented**
  (`app/connectors/pubmed.py`, `app/connectors/semantic_scholar.py`), reusing
  the same shared infra as arXiv/OpenAlex/Crossref (`BaseConnector`,
  `call_with_retry`, per-source `AsyncRateLimiter`, the in-memory response
  cache) plus Crossref's `normalize_doi` for DOI cleanup. `SourceEnum` /
  `SourceId` list five sources again; `CONNECTOR_FACTORIES` in
  `start_collection.py` wires both in, so requests naming either source reach
  a real connector rather than the orchestrator's "unregistered source"
  fallback. Covered by `test_pubmed_connector.py`,
  `test_semantic_scholar_connector.py`, and
  `test_connector_factories_wiring.py` (mocked HTTP via `pytest-httpx`; no
  live-run test suite entry, consistent with the other connectors). Known
  scope limits:
  - Neither has been run against the real API end-to-end through the
    orchestrator yet (only `scripts/check_pubmed_live.py` /
    `check_semantic_scholar_live.py`, the same manual-only pattern already
    used for arXiv/Crossref) — no live orchestrator run recorded for these
    two sources the way US-03.4's note above records one for arXiv+OpenAlex.
  - PubMed's `search()` makes two sequential HTTP requests per keyword
    (`esearch` then `efetch`), each independently rate-limited and retried;
    this roughly doubles PubMed's per-keyword latency relative to the
    single-request connectors and isn't reflected in any runtime budget/SLA
    doc yet.
  - Semantic Scholar's unauthenticated pool is shared globally across all API
    consumers, not just this app — the conservative 1 req/s default
    (`RATE_LIMIT_SEMANTIC_SCHOLAR_RPS`) is a guess, not a documented per-IP
    guarantee, so 429s are still possible under real-world load even with the
    limiter in place.
  - Both are frontend-selectable in `ConfigurePage` but default to
    **unchecked** (`defaultChecked: false`), unlike the original three
    sources — a deliberate choice so existing collection behavior doesn't
    change by default; not yet confirmed with product/UX as the permanent
    default.
- **Frontend is now wired to `POST /collections`.** `ConfigurePage.handleStart`
  calls the new `startCollection()` (`frontend/src/api/collections.ts`) and
  navigates to `/collections/:id/progress` on success, so `CollectionPage` is
  reachable end-to-end from the UI. Verified with the real backend (uvicorn)
  using the exact payload shape `ConfigurePage` sends: `POST /collections` →
  202 with `id` → polling `/progress` → `completed` with per-source detail,
  and the 422 error path (Pydantic `detail` list) surfaces correctly through
  `parseCollectionParamsError`. Not verified in an actual browser (no
  Vitest/RTL/Playwright set up yet in this repo despite being in the
  intended stack) — only via direct HTTP calls matching the frontend's own
  request/response contract.
- **Vitest + React Testing Library are now set up** (`frontend/package.json`,
  `frontend/vite.config.ts`'s `test` block, `frontend/src/setupTests.ts`),
  closing the gap noted just above. `npm test` runs the suite (`vitest run`).
  Only the custom-connector wizard and the pure `jsonPathSuggest` helper have
  tests so far — the rest of the frontend (`ConfigurePage`, `CollectionPage`,
  etc.) still has none.
- **Custom Connectors (EP-custom-connectors) are implemented**: a
  config-driven `GenericConnector` (`app/connectors/generic.py` +
  `generic_config.py`) lets a researcher add a JSON-based scientific source
  outside the 5 built-ins through `/sources/custom/new`, persisted in a new
  `custom_connectors` table and merged into the orchestrator's
  `connector_factories` dict alongside the built-ins
  (`app/connectors/registry.py`) — see `docs/custom-connectors.md` for the
  full design, the API research behind the config schema (IEEE Xplore, HAL,
  DOAJ, CORE, Europe PMC), and explicit scope limits (JSON only, no OAuth,
  one request per page, no field-level transforms beyond dot-path
  extraction, no secrets vault — API keys are stored as plaintext on disk,
  though a security review before merge caught and fixed two issues so they
  are never returned in plaintext or usable for SSRF, see below). Notable
  scope/behavior changes this required in shared code:
  - `RawArticle.source` / `ArticleClean.source` / `ConnectorError.source`
    widened from `SourceEnum` to `str` (`app/domain/entities.py`) so a
    custom connector's slug can flow through the same pipeline as the 5
    built-in sources. `SourceEnum` members are `StrEnum`, so this is a
    type-widening, not a behavior change, for the 5 built-in connectors.
  - `CollectionParamsRequest.sources` widened from `list[SourceId]` to
    `list[str]` (`app/schemas/collections.py`) — a request naming an
    unregistered source string (typo, or a since-deleted custom connector)
    is no longer a 422; it now reaches `POST /collections` and is reported
    as a failed source in `GET /collections/{id}/progress`, same as the
    orchestrator already does for any other unregistered source
    (`test_unregistered_source_is_marked_failed_without_blocking_others` in
    `test_orchestrator_runner.py`; see the renamed
    `test_unregistered_source_string_is_accepted_and_reported_as_a_failed_source`
    in `test_start_collection.py`).
  - Only the 5 built-in connector *files* were left untouched, per the
    constraint this feature was built under — `app/domain/entities.py` and
    `app/schemas/collections.py` (shared glue, not connector-specific code)
    were widened as described above.
  - The custom-connectors table has no Alembic migration yet, same
    `Base.metadata.create_all()` MVP tradeoff already noted for
    `collection_runs` above.
  - The "paste example JSON, suggest field paths" wizard helper
    (`frontend/src/lib/jsonPathSuggest.ts`) is a plain keyword-matching
    heuristic over the pasted sample's flattened field names — it does not
    call the backend and offers no guarantee of correctness; "test
    connection" against the real source is still the only way to confirm a
    mapping actually works.
  - **Two findings from a pre-merge security review were fixed, not just
    documented**, since `base_url`/auth are entirely researcher-supplied and
    every endpoint in this app (custom connectors included) has no auth of
    its own:
    1. Unauthenticated SSRF: `base_url` had no restriction beyond the
       `http(s)://` scheme, and `POST /custom-connectors/test` reflected the
       full raw response back to the caller — anyone reaching this backend
       could point it at the cloud metadata address or any internal
       service. Fixed with a two-layer host check: literal private/loopback/
       link-local IPs rejected at config-save time
       (`CustomConnectorConfig`'s validator, `app/connectors/generic_config.py::is_unsafe_ip`,
       no DNS needed), and a hostname that *resolves* to one of those ranges
       rejected at request time, before every `search()`/`test_connection()`/
       `health_check()` call (`app/connectors/generic.py::default_host_guard`,
       re-resolved per call rather than trusted from save time, to cover DNS
       rebinding). Does not protect against a public host that itself proxies
       to internal services, or a redirect chain (`GenericConnector` doesn't
       follow redirects, so that specific vector doesn't apply either).
       Covered by `test_generic_connector_ssrf.py`.
    2. Plaintext API key exposure: `GET /custom-connectors` and `.../{slug}`
       returned the full stored config, including `auth.key_value`, to any
       caller. Fixed by redacting `key_value` to `null` in every response and
       adding `auth_key_configured: bool` instead
       (`app/api/v1/custom_connectors.py::_to_response`); since the real value
       never comes back, a blank `key_value` on `PUT` now means "keep the
       existing key" rather than "clear it" (only switching `auth.type` to
       `none` clears it) — `app/use_cases/manage_custom_connectors.py::update_custom_connector`.
       Covered by the redaction/preserve/replace/clear tests in
       `test_custom_connectors.py`.
- **US-06.1 (Excel export) and US-06.2 (CSV/JSON export) are implemented.**
  `GET /api/v1/collections/{id}/export?format=xlsx|csv|json` accepts the same
  `sort`/`year_from`/`year_to`/`source`/`has_doi`/`has_abstract`/`keyword`
  query params as `GET .../articles`, so whatever the Results page's filter
  sidebar currently has active is exactly what gets exported - there is no
  separate "export scope" concept (`app/use_cases/export_dataset.py`,
  `app/exporters/{xlsx,csv,json}_exporter.py`). `.xlsx` has five sheets
  (`articles` = every matching row including duplicates, `deduped`,
  `duplicates`, `stats` recomputed over that same filtered set, `params`
  documenting the run + which filters/sort were active); every sheet's header
  row is bold with `freeze_panes="A2"`. `.csv` is written with the stdlib
  `csv` module, UTF-8 with a BOM (`utf-8-sig`) and `QUOTE_NONNUMERIC` so every
  string cell is quoted and numeric cells aren't. `.json` is a plain array of
  article records (list fields like `authors` stay real JSON arrays, unlike
  the semicolon-joined CSV/XLSX cells). The frontend (`ResultsPage.tsx`) has
  one button per format, per the AC, fetched as a blob (not a bare `<a href>`
  navigation) so a failed export surfaces as a visible error message instead
  of silently downloading a JSON error body as a fake `.xlsx`/`.csv` file.
  Covered by `test_exporters.py` (pure exporter unit tests),
  `test_exports_api.py` (endpoint + filter-propagation), and
  `ResultsPage.test.tsx`. Known scope limits:
  - `CollectionParamsRequest.include_missing_abstract` /
    `exclude_duplicates_on_export` (captured at collection-start time) are
    still not applied anywhere (pre-existing gap, noted above under
    US-03.4) - export filtering is entirely driven by the Results page's
    live filter state instead, which supersedes what those two fields were
    originally meant for.
  - No row/cell limit on the `.xlsx` writer; a very large corpus is written
    fully in-memory (`openpyxl.Workbook`) before being returned, same
    single-process MVP tradeoff already accepted elsewhere in this file.
- **Sprint 6 security review + functional test book (US-08.1/08.2-adjacent).**
  A full-codebase security pass (not scoped to one feature this time) found
  and fixed six issues — CSV/XLSX formula injection, unbounded keyword
  input, a custom-connector rate limiter not shared across concurrent runs,
  no cap on concurrent collections (+ unbounded in-memory progress-state
  growth), a hardcoded CORS origin, and four vulnerable frontend
  dependencies — see `docs/security-review.md` for full detail, including
  what was reviewed and already found safe (SSRF/API-key handling from the
  prior review, `javascript:` URI injection, SQL injection, secrets
  handling) and what's deferred (DNS-rebinding TOCTOU on the custom-connector
  host guard, `str(exc)` reaching `GET /collections/{id}/progress`). Ten
  Must-Have paths were also executed end-to-end against a live running
  stack (`docs/testing/functional-test-book.md`) — 10/10 pass; one
  mid-session investigation (a browser tab hang under a specific synthetic
  keyword pattern) was reproduced, root-caused to the browser's own
  spellchecker via a decisive counter-test, and resolved as not a product
  defect. **Still no login/user-account system anywhere in the stack** —
  every `/api/v1/*` endpoint remains unauthenticated by design (single-user
  internal tool); this pass hardened what's reachable given that, it did
  not add access control.
