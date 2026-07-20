"""
Compliance cap enforcement (US-03.7).

Pure, zero-I/O policy that the future orchestrator (US-03.4) applies to raw
connector output before persistence: truncate each (source, keyword) group
to at most `max_articles_per_keyword`, keeping fetch order, and report which
groups were actually truncated so callers can surface a UI warning.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.entities import RawArticle


@dataclass
class ComplianceCapResult:
    articles: list[RawArticle]
    capped_groups: list[tuple[str, str]] = field(default_factory=list)

    @property
    def cap_was_hit(self) -> bool:
        return len(self.capped_groups) > 0


def enforce_max_articles_per_keyword(
    articles: list[RawArticle], max_articles_per_keyword: int
) -> ComplianceCapResult:
    if max_articles_per_keyword < 1:
        raise ValueError("max_articles_per_keyword must be at least 1.")

    grouped: dict[tuple[str, str], list[RawArticle]] = {}
    for article in articles:
        grouped.setdefault((article.source, article.search_keyword), []).append(article)

    kept: list[RawArticle] = []
    capped_groups: list[tuple[str, str]] = []
    for key, group in grouped.items():
        if len(group) > max_articles_per_keyword:
            capped_groups.append(key)
        kept.extend(group[:max_articles_per_keyword])

    return ComplianceCapResult(articles=kept, capped_groups=capped_groups)
