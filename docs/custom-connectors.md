# Custom Connectors

The 5 built-in connectors (arXiv, Crossref, OpenAlex, PubMed, Semantic Scholar - see
[`docs/connectors.md`](connectors.md)) cover our MVP source list. **Custom Connectors** let a
researcher add a source we haven't pre-built - IEEE Xplore, HAL, DOAJ, CORE, Europe PMC, an
institutional repository, anything that returns JSON over HTTP - purely through configuration,
with no code change and no new deployment.

This is a separate feature from the 5 built-ins. None of `arxiv.py`, `crossref.py`,
`openalex.py`, `pubmed.py`, or `semantic_scholar.py` were touched to build it.

## How it works

- `backend/app/connectors/generic_config.py` - the config schema (`CustomConnectorConfig`) and
  `resolve_path()`, a small dot-path DSL for reaching into a JSON response. Pure, zero-I/O -
  unit-tested the same way `app/domain/*` is.
- `backend/app/connectors/generic.py` - `GenericConnector`, one class that implements
  `BaseConnector` (same contract as the 5 built-ins) entirely by interpreting a
  `CustomConnectorConfig` at request time. Reuses the same shared infrastructure the built-ins
  use: `app/infra/retries.py` (resilient HTTP layer, exponential backoff, max 2 retries),
  `app/orchestrator/rate_limiter.AsyncRateLimiter`, and `app/connectors/crossref.normalize_doi`.
- `custom_connectors` DB table (`app/db/models.py`) - persists `{name, slug, config, enabled,
  created_by, created_at, updated_at}`. `config` is the full `CustomConnectorConfig` as JSON.
- `app/connectors/registry.py::load_custom_connector_factories` - loads every **enabled** custom
  connector into a `{slug: factory}` dict, merged with the 5 built-in factories in
  `app/use_cases/start_collection.py` before every collection run. `app/orchestrator/runner.py`
  is completely unaware custom connectors exist - a request naming a custom slug reaches
  `GenericConnector.search()` through the exact same `connector_factories` dict lookup as a
  request naming `"arxiv"`. A disabled or deleted custom connector's slug simply isn't in the
  dict, which the orchestrator already handles (marks that source failed, continues with the
  others) - no custom-connector-specific logic exists there.
- `CollectionParamsRequest.sources` (`app/schemas/collections.py`) accepts any string, not just
  the 5 built-in ids, so a custom slug can be selected from `/collections/new` like any other
  source.

## The research behind the config schema

Before designing the schema, we looked at how much request/response shape actually varies
across real bibliographic APIs we don't support yet:

| Source | Auth | Pagination | Results location | Author field |
|---|---|---|---|---|
| **IEEE Xplore** ([docs](https://developer.ieee.org/docs)) | `apikey` query param on every request | `start_record` (offset-like) + `max_records` | flat `articles` array | nested: `authors.authors[].full_name` |
| **HAL** ([docs](https://api.archives-ouvertes.fr/docs/search)) | none | `start`/`rows` offset, or `cursorMark=*` for large sets | `response.docs` | flat array of strings: `authFullName_s` |
| **DOAJ** ([docs](https://doaj.org/api/docs)) | none for search | page-based | BibJSON: `bibjson.title`, `bibjson.author[].name` | nested array |
| **CORE** ([docs](https://api.core.ac.uk/docs/v3)) | Bearer token in `Authorization` header | `offset`/`limit`, response includes `totalHits` | flat `results` array | nested: `authors[].name` |
| **Europe PMC** ([docs](https://europepmc.org/RestfulWebService)) | none | `cursorMark` / `nextCursorMark` | `resultList.result` | **single joined string**: `authorString` (not an array) |

Three axes of variation fell out of this:

1. **Auth style**: none, an API key in a header (CORE), or an API key in the query string (IEEE).
2. **Pagination style**: page number, offset/limit, or cursor/token - and some sources (HAL) support
   more than one.
3. **Response shape**: fields can be flat (HAL's `title_s`) or nested (CORE's `authors[].name`,
   IEEE's `authors.authors[].full_name`), and "the author list" can be an array of objects, a
   flat array of strings, or a single comma-joined string (Europe PMC).

The config schema (`CustomConnectorConfig`) covers exactly these three axes: `auth.type`,
`pagination.style`, and a dot-path per target field (`resolve_path`, which supports `key`,
`key.nested`, and `key[].nested` for "map over this array"). See
`backend/tests/unit/test_generic_connector.py` for all three of HAL/CORE/Europe PMC's shapes
exercised end-to-end against mocked fixtures.

## What a custom connector can express

- `base_url`, `GET` or `POST`.
- Auth: none / API key in a named header / API key in a named query parameter.
- A query parameter for the search keyword, optional year-range parameters, and any number of
  constant static query parameters or static headers sent on every request.
- Pagination: page number, offset/limit, or cursor/token - with a configurable page size, a
  dot-path to the results array, an optional dot-path to a total-hit count (to stop cleanly),
  and a "shorter-than-requested page = last page" heuristic for sources with neither.
- A dot-path per target field: title (required), authors, year, abstract, DOI, citation count,
  URL, venue. Authors can be an array of objects (`authors[].name`), an array of strings
  (`authFullName_s`), or a single string (wrapped into a one-element list).
- A per-connector rate limit (requests/second) and connect/read timeouts.

## What it cannot express (by design, for the MVP)

- **JSON responses only.** No XML/Atom parsing (arXiv's connector needs bespoke XML handling
  for exactly this reason - that's why it stays a dedicated connector, not a config).
- **No OAuth or multi-step auth flows.** Only a static API key value in one header or query
  param. A source requiring OAuth2, signed requests, or a rotating token needs a dedicated
  connector.
- **One HTTP request per page.** PubMed's real connector needs two sequential requests per
  keyword (`esearch` then `efetch`) - that two-step protocol has no equivalent here.
- **No field-level transforms beyond path extraction.** A dot-path can extract and map-over
  arrays, but can't split a delimited string, run a regex, or compute a derived field. Europe
  PMC's `authorString: "Doe J, Smith J."` maps as a single one-element author list, not two
  authors - a real Europe PMC connector would need custom string-splitting logic this config
  format doesn't offer.
- **No secrets vault.** `auth.key_value` is stored as plaintext JSON in the `custom_connectors`
  table (fine for a single-team MVP; revisit before this is exposed beyond a trusted internal
  user base). It is **not**, however, ever returned by the management API: `GET
  /api/v1/custom-connectors` and `.../{slug}` redact `config.auth.key_value` to `null` and expose
  only `auth_key_configured: bool` instead (security review finding - this endpoint has no auth,
  so a stored third-party API key must never round-trip out through it in plaintext). The wizard
  shows "an API key is already saved - leave blank to keep it" rather than the real value on
  edit; leaving the key field blank on save preserves the existing key (only switching auth to
  "No authentication" clears it) - see `app/use_cases/manage_custom_connectors.py::update_custom_connector`.
  "Test connection" is unaffected by redaction (it's a stateless, non-persisted call using
  whatever is currently typed in the form), but note: when editing a connector with a saved key,
  testing *with that key* requires re-entering it - the wizard can't test with a secret it was
  never given back.
- **`base_url` is checked against SSRF, but only for network destinations, not paths.** Since
  `base_url` is entirely researcher-supplied and the backend makes live outbound requests to it
  (including from the unauthenticated `/custom-connectors/test` endpoint, which reflects the raw
  response back to the caller), a literal private/loopback/link-local/cloud-metadata IP is
  rejected at save time (`CustomConnectorConfig`'s validator, no DNS needed), and a hostname that
  *resolves* to one of those ranges is rejected at request time (`app.connectors.generic.default_host_guard`,
  called before every `search()`/`test_connection()`/`health_check()` - this also covers DNS
  rebinding, since it re-resolves on every call rather than trusting the save-time check). This
  does not protect against a public host that itself proxies to internal services, or non-IP-based
  SSRF vectors (e.g. a redirect chain - `GenericConnector` does not follow redirects).
- **No automatic polite-pool identification beyond `User-Agent`.** Built-in connectors send
  `mailto=` because their code adds it explicitly; a custom connector only gets a `User-Agent`
  header by default. If the source's usage policy requires a `mailto` param, add it yourself
  as a static query parameter.
- **Slugs are derived from the name and cannot collide with a built-in source id** (`arxiv`,
  `openalex`, `crossref`, `pubmed`, `semantic_scholar`) - `generate_unique_slug` appends `-2`,
  `-3`, etc. if needed.
- **The health check is shallow.** It's a single live request with `max_results=1`; a `200`
  response counts as healthy even if the field mapping is wrong - use "test connection" in the
  wizard to actually verify mapping correctness before saving.
- **The keyword must be a query parameter - not a URL path segment.** DOAJ's search endpoint is
  `GET /api/search/articles/<search terms>` (the keyword goes in the path, not `?q=...`), which
  this schema has no way to express. See the DOAJ entry under "Worked examples" below.

## The wizard (`/sources/custom/new`, `/sources/custom/:slug/edit`)

A dedicated page, not a modal - this is a one-time, multi-field setup with iterative
trial-and-error via "test connection", which doesn't fit a cramped dialog next to our other
5-6 screens.

1. **Basic Info & Auth** - name, base URL, HTTP method, the keyword query parameter,
   authentication, optional year-range parameters, rate limit, and any static query
   params/headers.
2. **Pagination** - pagination style and its parameters, where the results array lives in the
   response, an optional total-count field, and the short-page-is-last-page toggle.
3. **Field Mapping & Test** - map each target field to a dot-path, then run a live "test
   connection" against the real source: the researcher sees the request URL, the raw JSON
   response, and the `RawArticle` records the current mapping produces, before ever saving.

   A **paste-your-sample-JSON** helper is available on this step: paste one example response
   body and click "Suggest field paths from this sample" - it flattens the JSON client-side
   (`frontend/src/lib/jsonPathSuggest.ts`) and keyword-matches field names (`title`, `author`,
   `year`/`date`, `doi`, `abstract`, `cit...`, `url`/`link`, `venue`/`journal`/`publisher`) to
   suggest a dot-path per target field and the most likely `results_path`. It's a suggestion,
   not a guarantee - always confirm with "test connection" before saving.

Once saved, the connector appears in the source checklist on `/collections/new` next to the 5
built-ins, with a "Custom" badge, an edit pencil (back to the wizard, pre-filled), and a
health-check indicator. `/sources` is the dedicated management page: list, add, edit, delete,
health-check.

## Worked examples: configuring each researched source

Concrete wizard values for the sources in the research table above - useful both as a manual
test of the feature and as a starting point for actually onboarding one of these sources.

### HAL

No API key needed - this one works immediately.

**Step 1 - Basic Info & Auth**

| Field | Value |
|---|---|
| Source name | `HAL` |
| Base URL | `https://api.archives-ouvertes.fr/search/` |
| HTTP method | `GET` |
| Keyword query parameter | `q` |
| Authentication | No authentication |
| Static query parameters | `wt` → `json`  ·  `fl` → `title_s,authFullName_s,producedDateY_i,doiId_s,abstract_s` |

`fl` (field list) is required - HAL only returns `docid` + `label_s` by default; without `fl`
naming every field this connector needs, `title_s`/`authFullName_s`/etc. simply won't be in the
response at all.

**Step 2 - Pagination**

| Field | Value |
|---|---|
| Pagination style | Offset / limit |
| Page size | `20` |
| Page-size parameter | `rows` |
| Offset parameter | `start` |
| Starting offset | `0` |
| Results path | `response.docs` |
| Total-count field | *(leave empty)* |
| Treat shorter page as last | ✅ checked |

**Step 3 - Field Mapping**

| Field | Path |
|---|---|
| Title | `title_s` |
| Authors | `authFullName_s` |
| Publication year | `producedDateY_i` |
| DOI | `doiId_s` |
| Abstract | `abstract_s` |
| Citation count / URL / Venue | *(leave empty - not exposed by this query)* |

Gotcha: `title_s` and `abstract_s` are occasionally returned as one-element arrays rather than
plain strings (HAL's Solr schema treats them as multi-valued fields). If a mapped value looks
off, check "View raw response" during test-connection to confirm the exact shape for that
record.

### CORE

Needs a free API key from [core.ac.uk/services/api](https://core.ac.uk/services/api).

**Step 1 - Basic Info & Auth**

| Field | Value |
|---|---|
| Source name | `CORE` |
| Base URL | `https://api.core.ac.uk/v3/search/works` |
| HTTP method | `GET` |
| Keyword query parameter | `q` |
| Authentication | API key in a header |
| Header name | `Authorization` |
| API key / value | `Bearer <your-core-api-key>` (the word `Bearer`, a space, then the key) |

**Step 2 - Pagination**

| Field | Value |
|---|---|
| Pagination style | Offset / limit |
| Page size | `20` |
| Page-size parameter | `limit` |
| Offset parameter | `offset` |
| Starting offset | `0` |
| Results path | `results` |
| Total-count field | `totalHits` |
| Treat shorter page as last | ✅ checked |

**Step 3 - Field Mapping**

| Field | Path |
|---|---|
| Title | `title` |
| Authors | `authors[].name` |
| Publication year | `yearPublished` |
| DOI | `doi` |
| Abstract | `abstract` |
| Citation count | `citationCount` |
| URL / Venue | *(leave empty, or map `downloadUrl`/`publisher` if present on your account's response)* |

### Europe PMC

No API key needed.

**Step 1 - Basic Info & Auth**

| Field | Value |
|---|---|
| Source name | `Europe PMC` |
| Base URL | `https://www.ebi.ac.uk/europepmc/webservices/rest/search` |
| HTTP method | `GET` |
| Keyword query parameter | `query` |
| Authentication | No authentication |
| Static query parameters | `format` → `json`  ·  `resultType` → `core` |

`resultType=core` is required to get abstracts back - the default (`lite`) omits `abstractText`
entirely.

**Step 2 - Pagination**

| Field | Value |
|---|---|
| Pagination style | Cursor / next-page token |
| Page size | `20` |
| Page-size parameter | `pageSize` |
| Cursor parameter | `cursorMark` |
| Where the next cursor appears | `nextCursorMark` |
| Results path | `resultList.result` |

**Step 3 - Field Mapping**

| Field | Path |
|---|---|
| Title | `title` |
| Authors | `authorString` |
| Publication year | `pubYear` |
| DOI | `doi` |
| Abstract | `abstractText` |
| Citation count / URL / Venue | *(leave empty)* |

Gotcha: `authorString` is a single comma-joined string (e.g. `"Doe J, Smith J."`), not an array -
per the field-level-transforms limitation above, this maps as **one** author entry containing
the whole string, not two separate authors.

### IEEE Xplore

Needs a free API key from [developer.ieee.org](https://developer.ieee.org/) (registration
required).

**Step 1 - Basic Info & Auth**

| Field | Value |
|---|---|
| Source name | `IEEE Xplore` |
| Base URL | `https://ieeexploreapi.ieee.org/api/v1/search/articles` |
| HTTP method | `GET` |
| Keyword query parameter | `querytext` |
| Authentication | API key in the query string |
| Query parameter name | `apikey` |
| API key / value | `<your-ieee-api-key>` |

**Step 2 - Pagination**

| Field | Value |
|---|---|
| Pagination style | Offset / limit |
| Page size | `20` |
| Page-size parameter | `max_records` |
| Offset parameter | `start_record` |
| Starting offset | `1` (IEEE's record index is 1-based, not 0-based) |
| Results path | `articles` |
| Total-count field | *(leave empty)* |
| Treat shorter page as last | ✅ checked |

**Step 3 - Field Mapping**

| Field | Path |
|---|---|
| Title | `title` |
| Authors | `authors.authors[].full_name` |
| Publication year | `publication_year` |
| DOI | `doi` |
| Abstract | `abstract` |
| Citation count | `citing_paper_count` |
| URL / Venue | *(leave empty, or map `pdf_url`/`publication_title` if your account's response includes them)* |

### DOAJ - not currently expressible

DOAJ's search endpoint puts the keyword **in the URL path**, not a query parameter:
`GET https://doaj.org/api/search/articles/<search terms>`. Every other researched source (and
this config schema's `query_mapping.keyword_param`) assumes the keyword is a query string
parameter - there's no equivalent for "insert the keyword into the URL path" in the current
config format. DOAJ can't be onboarded as a custom connector without either a schema change
(a `path_template` option) or a dedicated connector file. Documented here rather than silently
omitted, since it's a real gap this feature's config format has.

## Test connection (`POST /api/v1/custom-connectors/test`)

Runs exactly one request against the configured (not-yet-saved) source and returns the request
URL, HTTP status, the raw response body, and the mapped `RawArticle` preview - all in one
response body, so a source-side failure (bad URL, rejected auth, timeout) comes back as
`success: false` with an error message rather than an HTTP error status.

## Cross-reference

See [`docs/connectors.md`](connectors.md) for the 5 built-in connectors' own details and the
shared infrastructure (`BaseConnector`, resilient HTTP layer, rate limiters, cache) both the
built-ins and `GenericConnector` are built on.
