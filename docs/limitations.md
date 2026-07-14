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
