import re


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