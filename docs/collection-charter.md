# Collection Charter (Appendix B)

The rules this platform follows when talking to external scientific APIs,
and how the code enforces each one. These are non-negotiable constraints on
every connector — built-in or custom — not aspirational guidelines.

## B.1 — Official APIs only

Every source is reached through its official, documented API
(arXiv's Atom API, OpenAlex's REST API, Crossref's REST API, PubMed's
E-utilities, Semantic Scholar's Graph API — see `docs/connectors.md` for
each one's endpoint and docs link). **No HTML scraping, no headless-browser
automation, and no anti-bot/CAPTCHA circumvention of any kind**, for the 5
built-ins or for a **Custom Connector** (`docs/custom-connectors.md`) — the
latter is explicitly JSON-over-HTTP only, by design, precisely so it can't
become a scraping backdoor.

## B.2 — No paywalled content

Connectors fetch **metadata** (title, authors, abstract, DOI, year,
venue, citation count) — never a full-text PDF, and never anything behind
a paywall or login. `RawArticle`/`ArticleClean` (`app/domain/entities.py`)
have no full-text field at all; there is nothing in the schema a connector
could even populate with paywalled content.

## B.3 — Duplicates are flagged, never deleted

Cross-source deduplication (`app/domain/deduplication.py`, US-04.2) marks
every duplicate it finds (`is_duplicate`, `duplicate_group_id`,
`duplicate_similarity_score`, `duplicate_rule` — see
`docs/data-dictionary.md`) but **never removes a row**. The default
article list view filters `is_duplicate = false` for readability, but the
full set (duplicates included) is always in the `articles` table and
always included in the `.xlsx` export's `articles` sheet (with a separate
`duplicates` sheet for just the flagged ones) — see US-06.1.

## B.4 — Missing data is flagged, never dropped

Normalization (`app/domain/cleaning.py::normalize_article`, US-04.1) sets
a missing field to `null` and lists it in `missing_fields`
(`build_missing_value_report`) — a record with no DOI or no abstract is
still persisted, never silently discarded. The Results UI surfaces this
with a badge + text label per field, never color alone (US-05.4, WCAG),
plus a persistent banner: *"Results are not exhaustive — the corpus is
limited by source coverage and API quotas."*

## B.5 — Identify the platform on every request

Every outbound HTTP call — from a built-in connector or a
`GenericConnector` — sends a `User-Agent` identifying this platform:

```
Team08-E26-Yonnovia/1.0 (mailto:<POLITE_POOL_EMAIL>)
```

OpenAlex and Crossref additionally require (and get) a `mailto=` query
parameter for their "polite pool" — a faster, more reliable tier reserved
for API consumers who identify themselves. PubMed and Semantic Scholar's
optional API keys (`PUBMED_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY`) work the
same way — identify yourself, get a better tier. `POLITE_POOL_EMAIL` is a
real, monitored address (`.env`), not a placeholder — see
`docs/connectors.md` for which sources require what.

## B.6 — Respect each source's rate limit

Every source has one shared `AsyncRateLimiter` instance
(`app/orchestrator/rate_limiter.py`) enforcing a minimum interval between
requests, sized to that source's documented ceiling:

| Source | Default rate | Config var |
|---|---|---|
| arXiv | 1 req / 3s | `RATE_LIMIT_ARXIV_INTERVAL_S` |
| OpenAlex | 10 req/s | `RATE_LIMIT_OPENALEX_RPS` |
| Crossref | 50 req/s (documented polite-pool ceiling) | `RATE_LIMIT_CROSSREF_RPS` |
| PubMed | 3 req/s (10 with an API key) | `RATE_LIMIT_PUBMED_RPS` |
| Semantic Scholar | 1 req/s (conservative — shared public pool) | `RATE_LIMIT_SEMANTIC_SCHOLAR_RPS` |
| Custom connector | 1 req/s default, configurable per connector (`rate_limit_rps`, max 50) | set in the wizard |

These limiters are **shared module-level singletons**, not per-request or
per-collection instances — so N collections running concurrently against
the same source still can't collectively exceed the configured rate. (This
was a real gap for custom connectors specifically until the Sprint 6
security review — see `docs/security-review.md` finding #3 — each
collection used to get its own limiter for a custom source; fixed to share
one per connector slug, same model as the built-ins.)

## B.7 — Resilient, bounded retries

`app/infra/retries.py::call_with_retry` (US-03.6), used by every connector:

- Retries **only** on `5xx`, `429` (rate-limited), and network/timeout
  errors.
- **Never** retries other `4xx` responses (`400`, `404`, etc.) — those are
  the caller's problem, not a transient failure, and are returned/raised
  as-is immediately.
- Exponential backoff: `100ms → 400ms → 1600ms`, **max 2 retries** (3
  attempts total).
- Every attempt logs its duration (structured JSON,
  `app/infra/logging.py`); a persistent failure logs a structured entry
  (`source`, `endpoint`, `keyword`, `error_class`) and raises
  `ConnectorError` rather than crashing.

## B.8 — One source failing never blocks the others

The orchestrator (`app/orchestrator/runner.py::run_collection`, US-03.4)
runs every selected source concurrently (`asyncio.gather`). A
`ConnectorError` from one source is caught, logged, and marks that source
`failed` in the run's progress — the collection continues with whatever
other sources are still running, and the run's final status becomes
`warning` (not `failed`) if at least one source succeeded.

## B.9 — Hard cap: 100 articles per keyword

`max_articles_per_keyword` is user-configurable (10–100) per collection,
but the platform enforces a **hard ceiling of 100** regardless of what's
requested — `CollectionParamsRequest` (`app/schemas/collections.py`)
rejects anything above 100 with a `422` before a run ever starts. As a
backstop (every connector already stops itself at `max_results`),
`app/domain/compliance.py::enforce_max_articles_per_keyword` re-truncates
any `(source, keyword)` group that still over-fetched, after the fan-out,
and surfaces a UI warning if that backstop actually had to fire.

## B.10 — Bounded input, bounded concurrency

Added in the Sprint 6 security review (`docs/security-review.md`) as
extensions of the spirit of B.6/B.9 — not just "don't ask a source for too
much per keyword," but "don't ask for too much, period":

- A collection can name **at most 50 keywords** (`CollectionParamsRequest.keywords`,
  each ≤ 200 characters) and **at most 50 sources**. The orchestrator runs
  a source's keywords strictly one at a time (B.6's shared rate limiter
  depends on this), so an unbounded keyword list would have meant an
  unbounded sequential run against every selected source.
- At most **10 collections can run concurrently** across the whole
  platform (`POST /collections` returns `429` past that) — protecting
  both this backend's own resources and, per B.6, every selected source's
  rate limit from being multiplied by however many collections happen to
  be running at once.

## Cross-reference

- Per-source specifics (endpoints, quirks, live-check scripts):
  `docs/connectors.md`.
- Custom-connector scope and its own compliance-relevant guard (SSRF
  protection on a fully researcher-supplied `base_url`):
  `docs/custom-connectors.md`.
- Full data model these rules populate: `docs/data-dictionary.md`.
- Latest security review, including what's fixed vs. deferred:
  `docs/security-review.md`.
