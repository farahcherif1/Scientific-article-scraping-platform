# Yonnov'IA — Team08-E26

Intelligent platform for collecting, cleaning, deduplicating, and exporting
scientific-article metadata from multiple official APIs (arXiv, OpenAlex,
Crossref, PubMed, Semantic Scholar — plus any JSON API you configure
yourself, no code required) from a single set of search keywords.

Give it keywords once, pick which sources to search, and get back a
cleaned, deduplicated, filterable, exportable corpus — instead of manually
querying each database and reconciling the results by hand.

## Status

Sprint 6 (final sprint) of an 8-week, two-developer academic project.
All planned epics (EP-01 through EP-08) are implemented; see
[`docs/limitations.md`](docs/limitations.md) for the itemized, honest list
of known scope limits, and [`docs/security-review.md`](docs/security-review.md)
+ [`docs/testing/functional-test-book.md`](docs/testing/functional-test-book.md)
for the latest security pass and end-to-end verification.

**CI:** every PR to `main`/`develop` runs backend lint+test and frontend
lint+test+build (`.github/workflows/ci.yml`) — currently 367 backend
(`pytest`) + 51 frontend (`vitest`) tests, both green.

## Quick start

```bash
git clone <this-repo-url> && cd team08-e26
cp backend/.env.example backend/.env    # then set POLITE_POOL_EMAIL
cp frontend/.env.example frontend/.env
docker compose up
```

Open **http://localhost:5173**. Full instructions (including a no-Docker
manual path and troubleshooting) in [`docs/install.md`](docs/install.md).

## What it does

1. **Enter keywords** — type/paste (comma, semicolon, or newline
   separated) or import from an Excel column; cleaned and
   case-insensitively deduplicated automatically.
2. **Pick sources** — arXiv, OpenAlex, Crossref, PubMed, and Semantic
   Scholar out of the box, no API key required for any of them; add any
   other JSON API through a no-code **Custom Connector** wizard.
3. **Collect** — every selected source is searched concurrently, with a
   live per-source progress view. One source failing never blocks the
   others, and every request respects that source's own rate limit and
   usage policy (see [`docs/collection-charter.md`](docs/collection-charter.md)).
4. **Automatic cleanup** — titles/authors/DOIs normalized, duplicates
   found across sources (DOI-exact or fuzzy-title matching) and flagged —
   never silently deleted.
5. **Explore** — a filterable, sortable results dashboard with KPIs, a
   per-year chart, missing-metadata warnings, and a relevance ranking.
6. **Export** — the exact filtered view, as a 5-sheet `.xlsx`, `.csv`, or
   `.json`.
7. **History** — every past collection, reopenable without re-running it.

See [`docs/user-guide.md`](docs/user-guide.md) for the full non-technical
walkthrough (under 15 minutes, start to export) and a 10-entry FAQ.

## Tech stack

**Backend:** FastAPI (Python 3.11+, async) · SQLAlchemy 2.0 · SQLite (MVP)
· httpx + tenacity · rapidfuzz · scikit-learn (TF-IDF) · openpyxl/stdlib
`csv` (no pandas) · pytest.
**Frontend:** React 18 + Vite + TypeScript · React Router · Tailwind CSS ·
Vitest + React Testing Library.
**Ops:** Docker Compose · GitHub Actions CI.

Full breakdown and Clean Architecture layering in
[`docs/architecture.md`](docs/architecture.md).

## Documentation index

| Doc | What's in it |
|---|---|
| [`docs/install.md`](docs/install.md) | Fresh-machine setup, Docker and manual paths, troubleshooting |
| [`docs/user-guide.md`](docs/user-guide.md) | Non-technical, end-to-end usage walkthrough + FAQ |
| [`docs/architecture.md`](docs/architecture.md) | Clean Architecture layers, directory layout, request-flow walkthrough |
| [`docs/data-dictionary.md`](docs/data-dictionary.md) | Full DB schema, domain entities, API response shapes |
| [`docs/collection-charter.md`](docs/collection-charter.md) | Compliance rules every outbound request follows, and how they're enforced in code |
| [`docs/connectors.md`](docs/connectors.md) | Per-source (arXiv/OpenAlex/Crossref/PubMed/Semantic Scholar) API details, quirks, live-check scripts |
| [`docs/custom-connectors.md`](docs/custom-connectors.md) | Config-driven "Custom Connector" design + worked examples (IEEE Xplore, HAL, DOAJ, CORE, Europe PMC) |
| [`docs/relevance.md`](docs/relevance.md) | Relevance-ranking formula |
| [`docs/security-review.md`](docs/security-review.md) | Latest security audit — findings fixed, reviewed-and-safe, and deferred |
| [`docs/testing/functional-test-book.md`](docs/testing/functional-test-book.md) | 10 Must-Have end-to-end scenarios, executed live |
| [`docs/limitations.md`](docs/limitations.md) | Itemized known scope limits, by story |

## Repository layout

```
backend/    FastAPI app, tests, Dockerfile — see docs/architecture.md
frontend/   React app, tests, Dockerfile — see frontend/README.md
docs/       Everything listed above
```

## Running the tests

```bash
cd backend && pytest -q && ruff check .
cd frontend && npm test -- --run && npm run lint && npm run build
```

## Compliance, in one sentence

Official APIs only, metadata only (no scraping, no paywalled content, no
anti-bot circumvention), every source's rate limit respected, every
request self-identifies (`User-Agent` + `mailto=`) — see
[`docs/collection-charter.md`](docs/collection-charter.md) for the full,
code-referenced rule set.
