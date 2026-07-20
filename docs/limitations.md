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
  - Only `arxiv`, `openalex`, and `crossref` have connectors. `semantic_scholar`
    is still schema-selectable (`SourceId`) but has no `CONNECTOR_FACTORIES`
    entry — the orchestrator reports it as a failed source (AC-compliant:
    doesn't block the other sources) rather than rejecting the request.
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
  - `app/orchestrator/rate_limiter.py` currently defines limiter instances
    for all four planned sources (OpenAlex/arXiv/CrossRef/PubMed) from
    `.env` config, even though only the OpenAlex connector exists so far —
    arXiv/CrossRef/PubMed connectors are still empty stub files.
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
