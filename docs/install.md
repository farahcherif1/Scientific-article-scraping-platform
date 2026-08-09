# Install Guide

Gets a fresh clone running end-to-end. Two paths: **Docker Compose**
(recommended — no local Python/Node version to manage) or **manual local
dev** (faster iteration once you're working in one stack).

## Prerequisites

| Path | Requirements |
|---|---|
| Docker Compose | Docker Desktop (or Docker Engine + Compose plugin) |
| Manual | Python 3.11+, Node.js (LTS — the frontend depends on Vite 8/Vitest 4, which need a current Node), `git` |

## 1. Clone and configure environment

```bash
git clone <this-repo-url>
cd team08-e26

cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

`backend/.env.example` and `frontend/.env.example` are the only files that
should ever be committed with real-looking values — `.env` itself is
gitignored (`*.env` in `.gitignore`) and must never be committed. Open
`backend/.env` and set:

```
POLITE_POOL_EMAIL=your-real-email@example.com
```

This is sent as the `mailto=` parameter to OpenAlex/Crossref and in every
connector's `User-Agent` header — it's how the platform identifies itself
to a "polite pool," not a secret (see `docs/collection-charter.md` B.5).
Everything else in `.env.example` has a sane default and doesn't need to
change for local dev. `PUBMED_API_KEY` / `SEMANTIC_SCHOLAR_API_KEY` are
optional — leave them blank to use the (slower) unauthenticated tier for
those two sources.

## 2a. Run with Docker Compose (recommended)

```bash
docker compose up
```

This builds and starts two containers:

- **backend** — FastAPI + `uvicorn --reload` on `http://localhost:8000`,
  with a `curl`-based healthcheck against `GET /health`.
- **frontend** — Vite dev server on `http://localhost:5173`, pointed at
  the backend via `VITE_API_BASE_URL` (set in `docker-compose.yml`, not
  `.env`, for the Compose path).

Both mount the source tree as a volume, so edits on the host are picked up
live (backend via `--reload`, frontend via Vite HMR) — no rebuild needed
for day-to-day changes, only for dependency changes (`pyproject.toml` /
`package.json`).

Open **http://localhost:5173** — you should land on `/keywords`. Confirm
the backend directly with:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

Stop with `Ctrl+C`, or `docker compose down` to also remove the containers
(the SQLite DB file lives on the host via the bind mount, so your data
survives either way — see "Resetting local data" below).

## 2b. Run manually (backend + frontend in separate terminals)

**Backend:**

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

**Frontend** (separate terminal):

```bash
cd frontend
npm install
npm run dev
```

Same URLs as the Docker path: backend on `:8000`, frontend on `:5173`.

## 3. Verify the install

```bash
# Backend: 367 tests, should all pass
cd backend && pytest -q

# Backend lint
ruff check .

# Frontend: 51 tests
cd frontend && npm test -- --run

# Frontend lint + production build
npm run lint
npm run build
```

All six should be clean on an unmodified checkout — this is exactly what
CI (`.github/workflows/ci.yml`) runs on every PR to `main`/`develop`.

## Try an end-to-end collection

1. Open `http://localhost:5173/keywords`, type a couple of keywords
   (comma/semicolon/newline-separated), click **Continue to
   Configuration**.
2. Leave arXiv/OpenAlex/Crossref checked (no API key needed for any of
   the 5 built-ins), set **Max articles per keyword** to something small
   like `10` for a fast first run, click **Start Collection**.
3. Watch the live per-source progress, then the Results dashboard — KPIs,
   a per-year chart, a filterable/sortable article table, and CSV/XLSX/JSON
   export buttons.

This makes real, live calls to arXiv/OpenAlex/Crossref's public APIs (per
`docs/collection-charter.md`) — no mocking, no API key required. See
`docs/user-guide.md` for the full non-technical walkthrough, or
`docs/testing/functional-test-book.md` for a scripted version of this same
path plus 9 more scenarios.

## Resetting local data

The SQLite file (`backend/team08.db`, path from `DB_URL` in `.env`) is
gitignored and created automatically on first backend startup
(`Base.metadata.create_all()`). To start from a clean slate — no
collections, no custom connectors — stop the backend and delete it:

```bash
rm backend/team08.db
```

It's recreated empty on the next startup.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `docker compose up` fails on the backend healthcheck | Check `docker compose logs backend` — a missing `backend/.env` (step 1) is the most common cause. |
| Frontend loads but every request fails / CORS error in the browser console | `CORS_ORIGINS` in `backend/.env` doesn't include the frontend's actual origin. Defaults to `http://localhost:5173`, which matches both install paths above — only relevant if you changed the frontend's port. |
| A live collection run returns 0 articles from every source | Check your network can reach `export.arxiv.org`, `api.openalex.org`, `api.crossref.org` directly (`curl` one of them) — these are real outbound calls, not mocked, so a firewall/proxy blocking them will surface here first. |
| `pytest` fails with import errors | You're not in the `backend/` directory, or the venv isn't activated / `pip install -e ".[dev]"` wasn't run. |
| `npm test`/`npm run build` fails with a Node version error | Node needs to be a current LTS — Vite 8 / Vitest 4 (this project's versions) don't support older Node majors. |

## Cross-reference

- Architecture and directory layout: `docs/architecture.md`.
- What each connector needs (API keys, ToU, rate limits, quirks):
  `docs/connectors.md`.
- Adding a source that isn't one of the 5 built-ins, no code required:
  `docs/custom-connectors.md`.
- Compliance rules every outbound request follows:
  `docs/collection-charter.md`.
- Known scope limits, by story: `docs/limitations.md`.
