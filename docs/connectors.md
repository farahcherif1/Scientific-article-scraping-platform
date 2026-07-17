# Scientific Source Connectors

This document tracks each connector's API details, rate limits, and how to verify it against the real (non-mocked) API before merging.

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
| **Rate limit** | ~1 request / 3 seconds (enforced in-connector via `asyncio.Lock` + `time.monotonic`) |
| **Domain coverage** | AI, CS, Math, Physics |

**Known quirks:**
- The `http://` variant of the endpoint 301-redirects to `https://`. The connector uses `https://` directly and also sets `follow_redirects=True` on the client as a safety net.
- `primary_category` lives in the arXiv-specific XML namespace (`http://arxiv.org/schemas/atom`), separate from the standard Atom namespace used for `title`, `author`, `summary`, etc. Both namespaces are parsed explicitly (`ATOM_NS` / `ARXIV_NS` constants).
- Some entries may lack `primary_category` — code degrades gracefully to `domain = None` rather than raising.

---

## OpenAlex

| | |
|---|---|
| **Status** | 🔲 Not yet implemented (US-03.2, owned by Ilyes) |

---

## Crossref

| | |
|---|---|
| **Status** | 🔲 Not yet implemented (US-03.3) |
| **API docs** | https://api.crossref.org/swagger-ui/index.html |
| **Endpoint** | `https://api.crossref.org/works` (JSON) |
| **Auth** | None (polite pool via `mailto=` param recommended) |
| **Rate limit** | 50 req/s (polite pool) per §3.1 of the Week 1 deliverable |
