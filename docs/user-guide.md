# User Guide

For anyone collecting scientific literature with this platform — no
technical background needed. Following this guide start-to-finish (enter
keywords → run a collection → filter results → export) takes under 15
minutes.

If you're setting the platform up yourself rather than just using it, see
`docs/install.md` instead.

## 1. Enter your keywords

Open the app — you land on **Define Scraper Keywords**.

- Type or paste keywords into the **Manual Keyword Entry** box, separated
  by commas, semicolons, or new lines — any mix works, e.g.:
  ```
  large language models
  retrieval-augmented generation, prompt engineering; transformer models
  ```
- The **Live Keyword Preview** panel on the right updates as you type,
  showing each keyword as a removable chip. Typos, extra spaces, and
  duplicates (even with different capitalization — `"AI"` and `"ai"` count
  as the same one) are cleaned up automatically; you never have to
  hand-dedupe a list.
- Already have a spreadsheet of search terms? Use **Import from Excel**
  instead — drag a `.xlsx` file in, pick which sheet and column holds your
  terms, and they're added to the same preview list (merged and
  deduplicated with anything you typed manually). An import report shows
  how many rows were kept vs. skipped (blank cells, duplicates) and why.
- Remove a keyword by clicking the **×** on its chip, or **Clear All** to
  start over.
- Click **Continue to Configuration** once your list looks right (at
  least one keyword is required; up to 50).

## 2. Configure the search

On **Configure Collection**:

- **Target Scientific Sources** — check which databases to search. arXiv,
  OpenAlex, and Crossref are pre-selected (no account needed for any of
  the 5 built-in sources: arXiv, OpenAlex, Crossref, PubMed, Semantic
  Scholar). At least one must stay checked.
- **Max articles per keyword** — a slider/stepper from 10 to 100. This is
  a *per keyword, per source* limit — with 3 keywords and 3 sources at the
  default of 50, that's up to 450 articles total. The platform enforces a
  hard ceiling of 100 per keyword regardless of what you set, to respect
  every source's usage policy (see `docs/collection-charter.md` if you're
  curious why).
- **Publication Date Range** *(optional)* — restrict results to articles
  published between two years.
- **Additional Filters** *(optional)* — a language or subject-domain hint
  (only applied where the underlying source supports it), plus two
  toggles: whether to keep articles with no abstract, and whether
  duplicates should be excluded from what you eventually export (they're
  never deleted from the results view either way — just flagged).
- The green **Configuration Valid** panel shows your selected keyword
  count, active source count, and maximum possible article yield, updated
  live as you change anything above.
- Click **Start Collection**.

## 3. Watch it collect

You're taken to a live progress screen: an overall percentage, which
keyword is currently being searched, and a per-source status card
(pending → running → done, or failed if that particular source hit a
problem — one source failing never stops the others). A typical small run
(a few keywords, 2–3 sources, 10–50 articles/keyword) finishes in seconds
to well under a minute. You can click **Abort Collection** at any point if
you started the wrong thing.

When it finishes, you're taken straight to the results.

## 4. Explore your results

The **Scraped Literature Corpus** page shows:

- A banner reminding you results aren't exhaustive — every source has its
  own coverage and rate limits, this is a sample of what's out there, not
  the whole literature.
- KPI cards: total articles, deduplicated count, duplicates found, % with
  a DOI, % with an abstract.
- A bar chart of articles published per year.
- A **Refine Corpus** sidebar: search within your results by keyword,
  narrow by publication year range, filter by source, or require a DOI
  and/or an abstract. Filters combine (all conditions must match), the
  table updates within a fraction of a second, and your filter choices
  are reflected in the page's URL — so you can bookmark or share a
  specific filtered view.
- The article table itself: title, venue/author line, year, source, DOI,
  citation count. A row missing its DOI or abstract shows a clearly
  labeled warning badge (not just a color, so it reads fine either way).
  Click any row to open a detail drawer with the full abstract and
  metadata.

## 5. Export

Three buttons, top-right of the results page: **XLSX**, **CSV**, **JSON**
— each downloads exactly the filtered/sorted set you're currently looking
at, not the full unfiltered corpus. The Excel file has five sheets:
`articles` (everything, including duplicates), `deduped`, `duplicates`,
`stats`, and `params` (a record of what keywords/sources/filters produced
this file).

## 6. Come back to it later

**History** (top nav) lists every collection you've ever run — keywords,
sources, article/duplicate counts, when it ran, and its status. Click any
row to reopen its results instantly, without re-collecting anything.

## Adding a source that isn't built in

If you need a database beyond the 5 built-in ones (IEEE Xplore, HAL,
DOAJ, CORE, Europe PMC, an institutional repository — anything that
returns JSON over HTTP), go to **Sources** → **Add Custom Source**. This
is a short setup wizard (base URL, how search results are structured,
which fields map to what) with a **Test Connection** step that shows you
real sample results before you save anything. See
`docs/custom-connectors.md` for worked, copy-pasteable examples for
several real sources, since this step needs some technical/API knowledge
to fill in correctly.

---

## FAQ

**1. Do I need an account or API key to use this?**
No. The app itself has no login. Of the 5 built-in sources, none require
an API key — PubMed and Semantic Scholar accept an *optional* key (set by
whoever deployed the platform, in its `.env` file) purely to get a faster
request tier; it changes nothing about how you use the app.

**2. Why did one of my sources come back with fewer results than
expected, or fail?**
Each source has its own coverage (e.g. PubMed is biomedical-only) and its
own request rate limit. A source can also fail a specific keyword (a
timeout, a temporary outage) — you'll see that source's card marked
"failed" on the progress screen and a "warning" status on the run, but
every other source's results are still there; nothing is blocked by one
source's problem.

**3. What does "not exhaustive" mean in the banner?**
Exactly what it says — this is a sample from each source's own index,
bounded by your per-keyword cap and each source's coverage. It's not a
claim to have found every paper on your topic in existence.

**4. Why do some articles have no DOI or no abstract?**
Not every source provides every field for every record — Crossref, for
example, rarely returns abstracts at all since its index is
metadata-first. Rather than silently dropping such an article, it's kept
and clearly flagged so you know what's missing and why.

**5. What counts as a duplicate, and can I still see them?**
An article found by more than one source (or the same source under
different search keywords) that shares a DOI, or has a near-identical
title (allowing for minor wording differences) published the same year,
is flagged as a duplicate of another. Duplicates are **never deleted** —
they're marked and excluded from the default view for readability, but
still counted in the KPIs and available in the export's `duplicates`
sheet.

**6. Can I run the same keywords again later?**
Yes — every run is independent and kept in History. Re-running the same
keywords starts a fresh collection (sources may have new articles since
last time) rather than reusing an old one.

**7. Does exporting change what's stored in the app?**
No. Exporting just downloads a snapshot of your current filtered view — it
doesn't delete, modify, or move anything in your results.

**8. How is the "relevance" sort computed?**
It's a keyword-frequency score: how many times your search keywords
appear in each article's title and abstract, summed across all your
keywords (a hit in the title counts the same as a hit in the abstract).
It's a simple heuristic, not an AI-based ranking — see `docs/relevance.md`
for the exact formula if you want the details.

**9. I have a large list of search terms in a spreadsheet — do I have to
retype them?**
No — use **Import from Excel** on the keyword page. Point it at the sheet
and column your terms are in; they're extracted, cleaned, and merged with
anything else already in your list.

**10. Something looks wrong / a page shows an error — what should I do?**
The app is designed to fail visibly rather than silently — an unknown
collection link, a failed export, or a rejected configuration all show a
clear message (often with a Retry button) instead of a blank page. If you
hit something that doesn't explain itself, check
`docs/limitations.md`/`docs/security-review.md` for a known, already-
documented cause first; if it's not listed there, it's worth reporting as
a bug (see `docs/testing/functional-test-book.md` for what a filed bug
report looks like on this project).
