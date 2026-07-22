"""
Cleaning / normalization functions (US-02.1 keyword cleaning + US-04.1
metadata normalization). Pure, zero-I/O per Clean Architecture: everything
here takes plain values in and returns plain values out.
"""
from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field

from app.domain.entities import ArticleClean, RawArticle

MAX_TITLE_LENGTH = 512

# Fields checked for presence when building an ArticleClean and its
# missing-value report (T-04.1.5). `title` and `authors` use emptiness
# (not just None) since normalization can reduce a garbage input to "".
_TRACKED_FIELDS = (
    "title",
    "authors",
    "year",
    "abstract",
    "doi",
    "url",
    "venue",
    "domain",
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_LATEX_CMD_WITH_ARG_RE = re.compile(r"\\[a-zA-Z]+\*?\s*\{([^{}]*)\}")
_LATEX_BARE_CMD_RE = re.compile(r"\\[a-zA-Z]+\*?")
_WHITESPACE_RE = re.compile(r"\s+")
_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "doi:")

MIN_PLAUSIBLE_YEAR = 1900


def clean_keywords(raw_keywords: list[str]) -> list[str]:
    """
    Normalize a list of raw keyword strings.
    - Strips whitespace
    - Drops empty entries
    - Deduplicates case-insensitively, keeping first occurrence's casing
    - Preserves unicode
    """
    seen: set[str] = set()
    cleaned: list[str] = []
    for kw in raw_keywords:
        stripped = kw.strip()
        if not stripped:
            continue
        key = stripped.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(stripped)
    return cleaned


def split_raw_keyword_string(raw: str) -> list[str]:
    """Split a raw string on newlines, commas, or semicolons, then clean."""
    parts = re.split(r"[\n,;]+", raw)
    return clean_keywords(parts)


# ---------------------------------------------------------------------------
# US-04.1 - metadata normalization
# ---------------------------------------------------------------------------


def _strip_markup(text: str) -> str:
    """
    Shared HTML/LaTeX/whitespace scrubbing used by title and abstract
    cleaning (T-04.1.1 / T-04.1.4).
    """
    cleaned = html.unescape(text)
    cleaned = _HTML_TAG_RE.sub("", cleaned)

    # LaTeX commands taking a brace argument (\textbf{Foo}, \emph{bar}) are
    # unwrapped to their argument. Looped a few times to peel simple nesting
    # like \textbf{\emph{Foo}} without a full LaTeX parser.
    for _ in range(5):
        unwrapped = _LATEX_CMD_WITH_ARG_RE.sub(r"\1", cleaned)
        if unwrapped == cleaned:
            break
        cleaned = unwrapped

    cleaned = cleaned.replace("$", "")
    cleaned = _LATEX_BARE_CMD_RE.sub("", cleaned)
    cleaned = cleaned.replace("\\", "")

    cleaned = unicodedata.normalize("NFKC", cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def normalize_title(raw_title: str | None) -> str:
    """
    Clean a raw title: unescape HTML entities, strip HTML/LaTeX markup,
    collapse whitespace, normalize to UTF-8/NFKC, and cap at 512 chars.
    """
    if not raw_title:
        return ""
    cleaned = _strip_markup(raw_title)
    if len(cleaned) > MAX_TITLE_LENGTH:
        cleaned = cleaned[:MAX_TITLE_LENGTH].rstrip()
    return cleaned


def normalize_abstract(raw_abstract: str | None) -> str | None:
    """Clean a raw abstract the same way as a title, but without the length cap."""
    if not raw_abstract:
        return None
    cleaned = _strip_markup(raw_abstract)
    return cleaned or None


def _is_all_caps(name: str) -> bool:
    letters = "".join(ch for ch in name if ch.isalpha())
    return bool(letters) and letters.isupper()


def normalize_author_name(raw_name: str) -> str | None:
    """
    Normalize one author string to a "First Last" entry, handling
    "First Last", "Last, First", and "ALL CAPS" input shapes.
    """
    name = _WHITESPACE_RE.sub(" ", raw_name or "").strip()
    if not name:
        return None

    if _is_all_caps(name):
        name = name.title()

    if "," in name:
        family, _, given = name.partition(",")
        family = family.strip()
        given = given.strip()
        name = f"{given} {family}".strip() if given and family else (family or given)

    name = _WHITESPACE_RE.sub(" ", name).strip()
    return name or None


def normalize_authors(raw_authors: list[str]) -> list[str]:
    """Normalize each author string, dropping any that turn out empty."""
    normalized = [normalize_author_name(author) for author in raw_authors]
    return [name for name in normalized if name]


def normalize_year(raw_year: int | None) -> int | None:
    """
    Pass through plausible publication years; anything outside a sane
    range (typos, placeholder values like 0 or 9999) is treated as missing
    rather than trusted.
    """
    if raw_year is None:
        return None
    if raw_year < MIN_PLAUSIBLE_YEAR or raw_year > 2100:
        return None
    return raw_year


def normalize_doi(raw_doi: str | None) -> str | None:
    """Strip the `https://doi.org/`-style prefix (any scheme/case) and lowercase."""
    if not raw_doi:
        return None
    value = raw_doi.strip()
    lowered = value.lower()
    for prefix in _DOI_PREFIXES:
        if lowered.startswith(prefix):
            value = value[len(prefix):]
            break
    value = value.strip().lower()
    return value or None


def _normalize_optional_text(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = _WHITESPACE_RE.sub(" ", raw).strip()
    return cleaned or None


def normalize_article(raw: RawArticle) -> ArticleClean:
    """
    Map a `RawArticle` (connector output) to an `ArticleClean`. Fields that
    end up empty/None after normalization are listed in `missing_fields`
    rather than silently dropped (AC: "never dropped").
    """
    fields = {
        "title": normalize_title(raw.title),
        "authors": normalize_authors(raw.authors),
        "year": normalize_year(raw.year),
        "abstract": normalize_abstract(raw.abstract),
        "doi": normalize_doi(raw.doi),
        "url": _normalize_optional_text(raw.url),
        "venue": _normalize_optional_text(raw.venue),
        "domain": _normalize_optional_text(raw.domain),
    }

    missing_fields = [name for name in _TRACKED_FIELDS if not fields[name]]

    return ArticleClean(
        **fields,
        categories=list(raw.categories),
        citation_count=raw.citation_count,
        source=raw.source,
        search_keyword=raw.search_keyword,
        collection_date=raw.collection_date,
        missing_fields=missing_fields,
    )


def normalize_articles(raw_articles: list[RawArticle]) -> list[ArticleClean]:
    return [normalize_article(article) for article in raw_articles]


@dataclass
class MissingValueReport:
    """Aggregate missing-field counts across a batch of normalized articles (T-04.1.5)."""

    total_articles: int
    missing_counts: dict[str, int] = field(default_factory=dict)
    missing_percentages: dict[str, float] = field(default_factory=dict)


def build_missing_value_report(articles: list[ArticleClean]) -> MissingValueReport:
    """
    Count, per field, how many normalized articles are missing it, plus the
    percentage of the batch that represents. Fields with zero occurrences
    are omitted from the dicts rather than reported as 0.
    """
    total = len(articles)
    counts: dict[str, int] = {}
    for article in articles:
        for field_name in article.missing_fields:
            counts[field_name] = counts.get(field_name, 0) + 1

    percentages = {
        field_name: round((count / total) * 100, 2) if total else 0.0
        for field_name, count in counts.items()
    }

    return MissingValueReport(
        total_articles=total,
        missing_counts=counts,
        missing_percentages=percentages,
    )