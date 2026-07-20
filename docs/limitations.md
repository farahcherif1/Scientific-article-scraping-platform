# Known Limitations

- **T-02.5.1 (History endpoint):** `GET /api/v1/history` reads from a new
  `collection_runs` table (`app/db/models.py`). There is no Alembic migration
  for it yet — tables are created via `Base.metadata.create_all()` on startup
  (`app/db/session.py:init_db`). This is fine for the SQLite MVP but should be
  replaced by a proper Alembic migration before the Postgres cutover.
- **Nothing populates `collection_runs` yet.** The multi-source orchestrator
  (US-03.4, Sprint 4) is what will insert a row per collection run. Until then,
  the history table is legitimately empty on a fresh clone — `HistoryPage`
  renders its empty state, not an error, in that case.
- Clicking a row in `HistoryPage` is wired to an `onOpenCollection(id)` callback
  but there is no Results view yet (US-05.1, Sprint 5) to reopen — it currently
  just navigates back to the Keywords page as a placeholder.
- **`CollectionPage` (progress UI, `frontend/src/pages/CollectionPage.tsx`) is
  unreachable end-to-end.** The route `/collections/:id/progress` and the
  `fetchCollectionProgress`/`abortCollection` API client functions
  (`frontend/src/api/collections.ts`) are built ahead of their backend, against
  the expected US-03.4 contract. Two things are missing before it works:
  - Backend: `GET /api/v1/collections/{id}/progress` and
    `POST /api/v1/collections/{id}/abort` don't exist yet
    (`backend/app/api/v1/collections.py` only has `POST /params/validate`).
    These land with the orchestrator (US-03.4, Sprint 4, T-03.4.1/T-03.4.4).
  - Frontend: `ConfigurePage.handleStart` only calls `validateCollectionParams`
    and shows a success message — it never creates a collection or navigates
    to `/collections/:id/progress`, so there's currently no `id` to reach this
    page with.
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
  - `app/infra/logging.py` (T-03.6.2, structured JSON log formatting) is
    still an empty stub. `retries.py` logs via stdlib `logging` with
    `extra={...}` fields today, but nothing configures a JSON formatter yet,
    so those extra fields won't render as JSON until that follow-up lands.
