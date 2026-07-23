from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.domain.entities import ArticleClean

_TITLE_CLEAN_RE = re.compile(r"[^a-z0-9 ]+")


@dataclass(frozen=True)
class DuplicateGroupAuditEntry:
    group_id: str
    canonical_index: int
    canonical_title: str
    canonical_doi: str | None
    rule: str
    score: int
    member_indices: list[int] = field(default_factory=list)


@dataclass
class DeduplicationResult:
    articles: list[ArticleClean]
    duplicate_count: int
    groups: list[DuplicateGroupAuditEntry]


def _clean_title_for_matching(title: str) -> str:
    normalized = title.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = _TITLE_CLEAN_RE.sub("", normalized)
    return normalized


def _author_similarity(a1: list[str], a2: list[str]) -> int:
    if not a1 or not a2:
        return 0
    joined1 = " ".join(a1).lower()
    joined2 = " ".join(a2).lower()
    return int(round(fuzz.token_sort_ratio(joined1, joined2)))


def _make_group_id(index: int) -> str:
    return f"DUP-{index:03d}"


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def deduplicate_articles(articles: list[ArticleClean]) -> DeduplicationResult:
    if not articles:
        return DeduplicationResult(articles=[], duplicate_count=0, groups=[])

    n = len(articles)
    uf = _UnionFind(n)
    match_info: dict[tuple[int, int], tuple[int, str]] = {}

    title_norms = [_clean_title_for_matching(article.title) for article in articles]

    # DOI exact groups take highest priority and are guaranteed score 100.
    doi_index_map: dict[str, list[int]] = {}
    for index, article in enumerate(articles):
        if article.doi:
            doi_index_map.setdefault(article.doi, []).append(index)

    for doi, indices in doi_index_map.items():
        if len(indices) <= 1:
            continue
        first = indices[0]
        for index in indices[1:]:
            uf.union(first, index)
            match_info[(min(first, index), max(first, index))] = (100, "doi_exact")

    for i in range(n):
        for j in range(i + 1, n):
            if articles[i].doi and articles[j].doi and articles[i].doi == articles[j].doi:
                continue

            left_title = title_norms[i]
            right_title = title_norms[j]
            if not left_title or not right_title:
                continue

            ratio = int(round(fuzz.ratio(left_title, right_title)))
            same_year = (
                articles[i].year is not None
                and articles[j].year is not None
                and articles[i].year == articles[j].year
            )
            authors_similarity = _author_similarity(articles[i].authors, articles[j].authors)

            rule: str | None = None
            score: int | None = None

            if same_year and ratio >= 92:
                rule = "title_fuzzy_same_year"
                score = ratio
            elif left_title == right_title and same_year:
                rule = "title_exact_same_year"
                score = 100
            elif left_title == right_title and authors_similarity >= 85:
                rule = "title_exact_authors_similar"
                score = max(90, min(99, authors_similarity))

            if rule is None:
                continue

            uf.union(i, j)
            match_info[(i, j)] = (score, rule)

    groups_by_root: dict[int, list[int]] = {}
    for index in range(n):
        root = uf.find(index)
        groups_by_root.setdefault(root, []).append(index)

    dedup_groups: list[DuplicateGroupAuditEntry] = []
    duplicate_count = 0
    article_group_stats: dict[int, tuple[str, int, str]] = {}

    for root, members in groups_by_root.items():
        if len(members) <= 1:
            continue

        group_id = _make_group_id(root + 1)
        canonical_index = min(members)
        canonical = articles[canonical_index]

        group_scores: list[tuple[int, str]] = []
        for a, b in itertools.combinations(sorted(members), 2):
            key = (a, b)
            if key in match_info:
                group_scores.append(match_info[key])

        if group_scores:
            score, rule = max(group_scores, key=lambda item: item[0])
        else:
            score, rule = (100, "grouped")

        dedup_groups.append(
            DuplicateGroupAuditEntry(
                group_id=group_id,
                canonical_index=canonical_index,
                canonical_title=canonical.title,
                canonical_doi=canonical.doi,
                rule=rule,
                score=score,
                member_indices=sorted(members),
            )
        )

        for index in members:
            article = articles[index]
            article.duplicate_group_id = group_id
            article.duplicate_similarity_score = score
            article.duplicate_rule = rule
            article.is_duplicate = index != canonical_index
            if index != canonical_index:
                duplicate_count += 1

    return DeduplicationResult(articles=articles, duplicate_count=duplicate_count, groups=dedup_groups)
