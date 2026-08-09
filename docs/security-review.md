# Security Review — Sprint 6 (2026-08-09)

Full-codebase security audit, performed by Ilyes Ben Jemaa alongside
US-08.1 (functional test book). **Scope, agreed up front:** harden the
platform's *existing* controls; this app has no login/user-account system
by design (see "Auth model" below), and adding one was explicitly out of
scope for this pass — anything here is about tightening what's already
there, not adding role-based access control.

This is the second security pass this project has had — the first (during
EP-custom-connectors, see `docs/limitations.md`) found and fixed an
unauthenticated-SSRF hole and a plaintext-API-key leak in the custom
connector feature. This pass covers the rest of the platform.

## Auth model (unchanged, by design)

Every `/api/v1/*` endpoint is unauthenticated — anyone who can reach the
backend can start collections, read/export any collection's data, and
manage custom connectors. This is a deliberate MVP tradeoff (single-user
internal tool, no `users` table, no session/token layer anywhere in the
stack) already called out in `docs/limitations.md` and reconfirmed with the
team before this review: **not** something this pass adds access control
to. Everything below assumes that trust boundary is unchanged and hardens
what happens *given* it.

## Method

- Manual read-through of every backend API route, the DB layer, the export
  pipeline, the custom-connector config/SSRF guard, and the orchestrator's
  concurrency/rate-limiting, looking for injection, SSRF, secrets handling,
  DoS/resource-exhaustion, and info-disclosure issues.
- Manual read-through of the frontend for XSS (`dangerouslySetInnerHTML`,
  raw `<a href>` from untrusted data, `eval`), and privacy hygiene.
- `pip-audit` against the backend's resolved dependencies.
- `npm audit` against the frontend's resolved dependencies.
- A live, browser-driven functional pass (`docs/testing/functional-test-book.md`)
  that exercises several of the fixes below end-to-end, not just at the
  unit-test level.

## Findings fixed this pass

| # | Finding | Severity | Fix |
|---|---|---|---|
| 1 | **CSV/Excel formula injection (CWE-1236).** Article titles/authors/venue (from any connector, built-in or fully researcher-configured) and a run's own keyword list were written into CSV/XLSX cells verbatim. A title like `=cmd|'/c calc'!A0` would execute as a live formula when the exported file is opened in Excel/Sheets/LibreOffice. | Medium | `app/exporters/common.py::sanitize_cell` prefixes a leading `=`/`+`/`-`/`@`/tab/CR with `'`, applied to every article cell (`article_to_flat_row`) and to the free-text fields of the XLSX params sheet (`keywords`, `filter_keyword`) — deliberately *not* applied to fixed/enum fields like `sort` (would otherwise mangle `"-relevance"`) or to the JSON export (never opened by spreadsheet software). Tests: `test_exporters.py` (`TestSanitizeCell`, plus one regression test per format). |
| 2 | **Unbounded keyword input (DoS-via-input).** `CollectionParamsRequest.keywords` had no length bound at all — a request could queue an arbitrarily long sequential per-source fan-out (the orchestrator runs a source's keywords one at a time). `KeywordParseRequest.raw_text` was similarly an unbounded string. | Medium | Added `max_length=50` on `keywords` (+ a 200-char-per-item validator) and `max_length=50_000` on `raw_text`. `sources` also capped at 50. Tests: `test_collection_params.py`, `test_keywords.py`. Verified live end-to-end in `docs/testing/functional-test-book.md` TC-10 — a 51-keyword submission is rejected with a clear `422` before any run starts. |
| 3 | **Custom-connector rate limiter not shared across concurrent runs.** Built-in connectors share one module-level `AsyncRateLimiter` per source, so the configured RPS holds even under concurrent collections. `GenericConnector` (custom connectors) got a *new* limiter every time its factory was called, so N concurrent collections against the same custom source could send up to N× the configured `rate_limit_rps` — a compliance-charter violation risk, and unfair to the third-party source. | Medium | `app/connectors/registry.py` now caches one `AsyncRateLimiter` per `(slug, rate_limit_rps)` and threads it into every `GenericConnector` built for that slug — same sharing model as the built-ins, and a rate-limit edit still takes effect on the next run (new cache key) rather than being stuck behind a stale limiter. Tests: `test_registry.py`. |
| 4 | **No concurrency cap on `POST /collections` + unbounded progress-state memory.** Nothing stopped a client from starting unboundedly many concurrent collections (each its own keyword×source fan-out against real third-party APIs — resource exhaustion here, rate-limit-charter risk there). Separately, `app/orchestrator/state.py`'s in-memory `_STORE` kept every collection ever started, for the life of the process, with no eviction — a slow memory leak under any sustained use. | Medium | `POST /collections` now checks `state_store.count_running() >= MAX_CONCURRENT_RUNNING` (10) and returns `429` instead of queuing another run. `_STORE` now evicts the oldest *finished* entries (never a running one) once it passes `MAX_STORE_SIZE` (500). Tests: `test_orchestrator_state.py`, `test_start_collection.py`. |
| 5 | **CORS origin hardcoded in code.** `app/main.py` hardcoded `allow_origins=["http://localhost:5173"]` — safely restrictive for dev, but a production deployment with a different frontend origin needed a code change, not a config change. | Low | Moved to `Settings.cors_origins` (comma-separated env var, `CORS_ORIGINS`), defaulting to the same dev origin. Tests: `test_config.py`. |
| 6 | **4 known-vulnerable frontend dependencies** (`npm audit`): `nanoid` (non-secure-generator DoS, 2 advisories), `postcss` (source-map path traversal / arbitrary-file-disclosure), `react-router`/`react-router-dom` (RSC-mode CSRF bypass). All transitive or minor-version-behind. | Medium (aggregate) | `npm audit fix` — all 4 resolved via patch/minor bumps within the existing `^` semver ranges (`package-lock.json` only; no `package.json` changes, no breaking changes). `npm audit` now reports 0 vulnerabilities. Full frontend suite (51 tests), lint, and `vite build` re-verified green after the bump. |

`pip-audit` on the backend found no vulnerabilities in any runtime
dependency (only `pip` itself, the packaging tool — irrelevant to the
deployed app).

## Findings reviewed and confirmed already handled (no action needed)

Called out explicitly so this doesn't look like it was missed:

- **SSRF on custom connectors** and **plaintext API key exposure** — both
  already found and fixed in a prior review (`docs/limitations.md`,
  EP-custom-connectors section). Re-verified: the two-layer host guard
  (`generic_config.py::is_unsafe_ip`, `generic.py::default_host_guard`) and
  the `auth.key_value` redaction (`custom_connectors.py::_to_response`) are
  both still in place and covered by `test_generic_connector_ssrf.py` /
  `test_custom_connectors.py`.
- **`javascript:` URI injection via article links.** `ResultsPage.tsx`'s
  detail drawer already gates every article URL through `isSafeHttpUrl`
  (only `http:`/`https:` render as a clickable `<a href>`; anything else —
  including `javascript:` — renders as inert text). Covered by
  `ResultsPage.test.tsx`.
- **SQL injection.** No raw SQL string interpolation anywhere in the
  codebase (verified by grep) — SQLAlchemy ORM/query-builder throughout.
- **Secrets in the repo.** `.env` (real values) is gitignored and not
  tracked; only `.env.example` (placeholder values) is committed. No
  hardcoded credentials found anywhere in `app/`.
- **HTML/script injection via React.** No `dangerouslySetInnerHTML`, no
  `eval`, no `new Function` anywhere in `frontend/src` — React's default
  escaping covers every other rendered field.

## Residual/deferred risk (documented, not fixed this pass)

- **DNS-rebinding TOCTOU on the custom-connector host guard.**
  `default_host_guard` re-resolves and re-checks the hostname once per
  `search()`/`test_connection()` call, but `httpx`'s own connection a
  moment later does an independent resolution — a DNS server timed to flip
  from a public to a private IP between those two lookups could theoretically
  slip through. This tradeoff is already called out explicitly in
  `generic.py`'s docstring (cost of full per-page pinning vs. one
  resolution per call). Left as-is: closing it fully needs a custom `httpx`
  transport that connects to the pre-resolved IP directly, which is a
  larger change than "harden existing controls" scope for this pass.
- **Exception messages surfaced to unauthenticated callers.**
  `run_collection_in_background`'s crash handler sets
  `state.error = str(exc)`, which reaches `GET /collections/{id}/progress`
  verbatim. Given there's no auth boundary on that endpoint anyway (see
  "Auth model" above), this is a minor incremental information-disclosure
  risk, not a new one — noted for awareness, not changed, to avoid touching
  error-handling behavior other tests/UI depend on without a dedicated pass.
- **Frontend page test coverage.** `docs/limitations.md` already notes only
  the custom-connector wizard, `jsonPathSuggest`, `Select`, `ArticlesPerYearChart`,
  and `ResultsPage` have automated tests; `ConfigurePage`, `CollectionPage`,
  `KeywordsPage`, `HistoryPage`, and `SourcesPage` still don't. Not a
  security gap specifically (all five were exercised manually, end-to-end,
  in `docs/testing/functional-test-book.md` and came back clean), but
  flagged here since it's the main reason this pass leaned on a live
  browser walkthrough for those pages rather than only `pytest`/`vitest`.

## Verification

- Backend: `pytest` — **367 passed** (up from 334; 33 new tests added for
  the fixes above), `ruff check` clean.
- Frontend: `vitest run` — **51 passed**, `eslint` clean, `vite build`
  succeeds, `npm audit` — **0 vulnerabilities**.
- Live: `docs/testing/functional-test-book.md` — 10/10 Must-Have paths
  pass against a real running stack, including two scenarios (TC-03, TC-10)
  that specifically exercise this sprint's changes end-to-end.
