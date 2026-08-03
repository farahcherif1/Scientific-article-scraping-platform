"""
Basic relevance ranking (US-04.3). Pure, zero-I/O per Clean Architecture:
scores a normalized article against the keyword list a collection was run
with. See docs/relevance.md for the documented formula.
"""
from __future__ import annotations

import re


def compute_relevance_score(title: str, abstract: str | None, keywords: list[str]) -> int:
    """
    Relevance score = the total number of times the collection's search
    keywords appear in the article's title + abstract, case-insensitive,
    matched on word boundaries (so "AI" doesn't match inside "chair").
    Each keyword's occurrences are counted independently and summed, so a
    keyword appearing in both the title and the abstract counts twice.
    """
    text = f"{title} {abstract or ''}"
    score = 0
    for keyword in keywords:
        cleaned = keyword.strip()
        if not cleaned:
            continue
        pattern = re.compile(rf"\b{re.escape(cleaned)}\b", re.IGNORECASE)
        score += len(pattern.findall(text))
    return score
