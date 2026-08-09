# Data Dictionary (Appendix A)

Schema reference for the SQLite database (`backend/team08.db`, path from
`DB_URL` in `.env`) and the domain entities that produce it. Source of
truth is always `backend/app/db/models.py` / `backend/app/domain/entities.py`
— this document explains what the columns mean and how they're populated,
not a substitute for reading the code.

No Alembic migration exists yet for any table — they're created via
`Base.metadata.create_all()` on startup (`app/db/session.py::init_db`). See
`docs/limitations.md`.

## `collection_runs`

One row per collection request (`POST /api/v1/collections`). This is what
`/history` lists and what a `COL-XXXX` id resolves to.

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER` PK, autoincrement | Internal numeric id. |
| *(computed)* `public_id` | — | `f"COL-{id:04d}"` — the id used everywhere in the API/URLs (`CollectionRun.public_id` property). `CollectionRun.numeric_id()` parses it back. |
| `keywords` | `JSON` (`list[str]`) | The exact keyword list the run was started with — echoed in History, used for `relevance_score` computation and the XLSX `params` sheet. |
| `sources` | `JSON` (`list[str]`) | Selected source ids — one of the 5 built-in `SourceId` values or a custom connector's slug. |
| `article_count` | `INTEGER`, default `0` | Total articles persisted for this run (duplicates included). Set once, when the background task finishes. |
| `duplicate_count` | `INTEGER`, default `0` | How many persisted articles are flagged `is_duplicate = true`. |
| `status` | `VARCHAR(20)` | One of `running` / `completed` / `warning` / `failed` (`CollectionStatus` enum). `warning` = completed but ≥1 source failed. |
| `created_at` | `DATETIME` (tz-aware, UTC) | Set at creation, before the fan-out starts. |

## `articles`

One row per `ArticleClean` produced by the normalize → deduplicate
pipeline for one collection run. **Every** collected article is persisted,
including duplicates — nothing is ever deleted (Collection Charter B.3).

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER` PK, autoincrement | |
| `collection_run_id` | `INTEGER` FK → `collection_runs.id` | Indexed (`ix_articles_collection_run_id`). |
| `title` | `VARCHAR(512)` | Normalized (HTML entities/LaTeX macros/whitespace stripped), never empty — falls back to `""` if a source returned nothing, never `null`. |
| `authors` | `JSON` (`list[str]`) | Normalized to `"First Last"` form regardless of source format (`"Last, First"`, `"FIRST LAST"`, etc. — see `app/domain/cleaning.py::normalize_author_name`). |
| `year` | `INTEGER`, nullable | Indexed (`ix_articles_year`). `null` + listed in `missing_fields` if the source didn't provide one. |
| `abstract` | `TEXT`, nullable | Markup-stripped. `null` (not dropped) if absent. |
| `url` | `VARCHAR(2048)`, nullable | Only ever rendered as a link in the UI if it parses as `http:`/`https:` (`isSafeHttpUrl` in `ResultsPage.tsx` — a `javascript:` or other scheme renders as inert text). |
| `doi` | `VARCHAR(255)`, nullable | `https://doi.org/` prefix stripped, lowercased. Indexed (`ix_articles_doi`). |
| `venue` | `VARCHAR(500)`, nullable | Journal/conference/venue name, where the source exposes one. |
| `domain` | `VARCHAR(255)`, nullable | Source-specific: arXiv's `primary_category`, OpenAlex's first `concepts` entry, Semantic Scholar's first `fieldsOfStudy` entry. |
| `categories` | `JSON` (`list[str]`) | Broader subject tags, where the source exposes them (e.g. arXiv's full category list). |
| `citation_count` | `INTEGER`, nullable | From the source (e.g. OpenAlex's `cited_by_count`); `null` where not exposed. |
| `keywords` | `JSON` (`list[str]`) | Author-/source-supplied keywords, cleaned. Usually empty — most sources don't expose this. |
| `keywords_auto` | `JSON` (`list[str]`) | TF-IDF-extracted phrases from the abstract (`app/domain/enrichment.py`), 3–7 phrases, English+French stop-words removed. Empty if there's no abstract. |
| `source` | `VARCHAR(100)` | Which connector produced this record — one of the 5 built-in ids or a custom connector's slug. Indexed (`ix_articles_source`). |
| `search_keyword` | `VARCHAR(200)` | Which single keyword (from the run's list) retrieved this specific article from its source. |
| `collection_date` | `DATETIME` (tz-aware, UTC) | When this record was fetched. |
| `duplicate_group_id` | `VARCHAR(20)`, nullable | `"DUP-###"` shared by every member of a duplicate group; `null` if this article matched nothing. See "Duplicate detection" below. |
| `duplicate_similarity_score` | `INTEGER`, nullable | 0–100. `100` for a DOI-exact or identical-title-same-year match; the rapidfuzz ratio otherwise. |
| `duplicate_rule` | `VARCHAR(50)`, nullable | Which rule matched this article into its group — `doi_exact`, `title_exact_same_year`, `title_fuzzy_same_year`, or `title_exact_authors_similar`. |
| `is_duplicate` | `BOOLEAN`, default `false` | `false` for exactly one "canonical" member per group (the lowest-index one seen), `true` for every other member. Indexed (`ix_articles_is_duplicate`) — the default article list view filters `is_duplicate = false`. |
| `missing_fields` | `JSON` (`list[str]`) | Which of `year`/`abstract`/`doi`/etc. were absent and set to `null`, per `app/domain/cleaning.py::build_missing_value_report`. Drives the UI's missing-metadata badges (US-05.4). |
| `relevance_score` | `INTEGER`, default `0` | Computed once at persistence time against the run's full keyword list (see `docs/relevance.md`). Indexed (`ix_articles_relevance_score`) since it's the default sort. |

### Duplicate detection, concretely

`app/domain/deduplication.py::deduplicate_articles` runs **within** one
collection's article set (not across collections). Matching, in priority
order:

1. **DOI exact** — identical normalized DOI → score `100`, rule
   `doi_exact`.
2. **Title exact + same year** → score `100`, rule
   `title_exact_same_year`.
3. **Title fuzzy (rapidfuzz `ratio` ≥ 92) + same year** → score = the
   ratio, rule `title_fuzzy_same_year`.
4. **Title exact + author-list similarity ≥ 85** (rapidfuzz
   `token_sort_ratio` over the joined author strings, used when year is
   missing on one or both sides) → score = `max(90, min(99, similarity))`,
   rule `title_exact_authors_similar`.

Matches are unioned transitively (union-find), so if A matches B and B
matches C, all three land in one group even if A and C weren't directly
compared as a match. The group's `duplicate_group_id` is `DUP-{root+1:03d}`
and its canonical member is whichever article has the lowest index in the
original collected order.

## `custom_connectors`

One row per researcher-configured source (see `docs/custom-connectors.md`).

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER` PK, autoincrement | |
| `name` | `VARCHAR(200)` | Display name, as entered in the wizard. |
| `slug` | `VARCHAR(64)`, unique | Derived from `name` (`generate_unique_slug`); this is what appears in `CollectionParamsRequest.sources` to select this connector. Cannot collide with a built-in source id (`arxiv`, `openalex`, `crossref`, `pubmed`, `semantic_scholar`). |
| `config` | `JSON` | The full, validated `CustomConnectorConfig` (`app/connectors/generic_config.py`) — auth, pagination, field mapping, headers, rate limit, timeouts. **`config.auth.key_value` is stored here in plaintext** (no secrets vault in the MVP — see `docs/custom-connectors.md` "What it cannot express") but is redacted to `null` on every read through the API. |
| `enabled` | `BOOLEAN`, default `true` | Disabled connectors are simply excluded from the orchestrator's factory dict — they're not deleted, and a request naming a disabled slug is reported as a failed source rather than a 422. |
| `created_by` | `VARCHAR(200)`, nullable | Freeform, not tied to any auth system (there isn't one). |
| `created_at` / `updated_at` | `DATETIME` (tz-aware, UTC) | `updated_at` auto-refreshes on save. |

## Domain entities (in-memory, not persisted as-is)

Two Pydantic models in `app/domain/entities.py` sit between "what a
connector returns" and "what's in the `articles` table":

- **`RawArticle`** — the common shape every connector (built-in or custom)
  maps its source-specific response into. Unnormalized: whatever the
  source actually sent (HTML entities in titles, `"Last, First"` author
  strings, etc.).
- **`ArticleClean`** — `RawArticle` after `app/domain/cleaning.py::normalize_article`
  and `app/domain/deduplication.py::deduplicate_articles`. This is what
  gets persisted into `articles`, field-for-field (plus the computed
  `relevance_score` and `keywords_auto`, added at persistence time — see
  `docs/architecture.md`'s request-flow walkthrough).

## API response shapes

- **Listing envelope** (History, custom connectors, articles):
  `{"data": [...], "pagination": {"total", "page", "page_size"}, "sort": "...", "filters": {...}}`.
- **`ArticleItem`** (`GET /collections/{id}/articles`) — every `articles`
  column above, plus two request-time-only computed fields not stored in
  the DB: `text_unified` (title + abstract + search_keyword, space-joined
  — the flat text blob AI-ready exports use) and `abstract_missing`
  (`bool`, `not bool(abstract)`).
- **`CollectionStatsResponse`** (`GET /collections/{id}/stats`) — `total`,
  `deduped`, `duplicates`, `pct_with_doi`, `pct_with_abstract`, plus
  `per_source` (count + the same three percentages, per source) and
  `articles_per_year` (`[{year, count}, ...]`, feeds the dashboard chart).
- **Framework-level error shape**: FastAPI/Pydantic validation errors
  (`422`) use FastAPI's default `{"detail": [...]}` shape (a list of
  Pydantic error objects), not the `{"error": {"code", "message"}}`
  envelope described in `docs/architecture.md` — that envelope is a
  convention for application-raised errors (`HTTPException(status_code=...,
  detail="...")`, which FastAPI renders as `{"detail": "..."}`, a string).
  The frontend's error parsers (`frontend/src/api/*.ts`) handle both
  shapes.

## Cross-reference

- Full compliance/collection rules these fields exist to enforce:
  `docs/collection-charter.md`.
- Per-connector field-mapping quirks (what each source actually returns
  before normalization): `docs/connectors.md`.
- Custom-connector config schema in full: `docs/custom-connectors.md`.
- Relevance scoring formula: `docs/relevance.md`.
