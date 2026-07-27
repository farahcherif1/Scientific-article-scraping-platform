# Known Limitations

- **T-02.5.1 (History endpoint):** `GET /api/v1/history` reads from a new
  `collection_runs` table (`app/db/models.py`). There is no Alembic migration
  for it yet — tables are created via `Base.metadata.create_all()` on startup
  (`app/db/session.py:init_db`). This is fine for the SQLite MVP but should be
  replaced by a proper Alembic migration before the Postgres cutover.
- Clicking a row in `HistoryPage` is wired to an `onOpenCollection(id)` callback
  but there is no Results view yet (US-05.1, Sprint 5) to reopen — it currently
  just navigates back to the Keywords page as a placeholder.
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
- **US-04.1 (metadata normalization) is implemented as pure domain functions,
  not yet wired into the collection pipeline.** `app/domain/cleaning.py` adds
  `normalize_title`, `normalize_authors`, `normalize_year`, `normalize_doi`,
  `normalize_abstract`, `normalize_article`/`normalize_articles`, and
  `build_missing_value_report`, mapping `RawArticle` -> the new
  `ArticleClean` entity (`app/domain/entities.py`). Covered by 38 unit tests
  in `test_metadata_normalization.py` (happy path + malformed-input edge
  cases per field, plus the missing-value report). Not yet called from
  `app/orchestrator/runner.py::run_collection` or `start_collection.py`:
  there is still no `articles` table and no endpoint to read collected
  articles back (see the `COL-000x` progress-only limitation above), so
  wiring normalization into the pipeline today would have no observable
  effect - it belongs with whichever story adds article persistence
  (US-05.1 territory) rather than with US-04.1's own subtasks.
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
  extraction, no secrets vault — API keys round-trip in plaintext through
  the management API). Notable scope/behavior changes this required in
  shared code:
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
