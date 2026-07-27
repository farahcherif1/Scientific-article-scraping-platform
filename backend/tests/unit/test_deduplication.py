from datetime import UTC, datetime

from app.domain.cleaning import normalize_articles
from app.domain.deduplication import deduplicate_articles
from app.domain.entities import RawArticle, SourceEnum

COLLECTED_AT = datetime.now(UTC)


def _raw(**overrides) -> RawArticle:
    defaults = {
        "title": "A Title",
        "source": SourceEnum.ARXIV,
        "search_keyword": "ai",
        "collection_date": COLLECTED_AT,
    }
    defaults.update(overrides)
    return RawArticle(**defaults)


def test_doi_exact_duplicates_get_same_group_and_score_100():
    articles = normalize_articles(
        [
            _raw(title="Deep Learning for Vision", doi="https://doi.org/10.1000/xyz"),
            _raw(title="Deep Learning for Vision", doi="10.1000/xyz"),
        ]
    )

    result = deduplicate_articles(articles)

    assert result.duplicate_count == 1
    assert len(result.groups) == 1
    group = result.groups[0]
    assert group.score == 100
    assert group.rule == "doi_exact"
    assert group.member_indices == [0, 1]
    assert articles[0].duplicate_group_id == articles[1].duplicate_group_id
    assert articles[0].duplicate_similarity_score == 100
    assert articles[1].duplicate_similarity_score == 100
    assert articles[0].is_duplicate is False
    assert articles[1].is_duplicate is True


def test_fuzzy_title_same_year_groups_with_score():
    articles = normalize_articles(
        [
            _raw(title="A robust study of deep learning", year=2022),
            _raw(title="A robust study of deep-learning", year=2022),
            _raw(title="A different paper", year=2022),
        ]
    )

    result = deduplicate_articles(articles)

    assert result.duplicate_count == 1
    assert len(result.groups) == 1
    group = result.groups[0]
    assert group.rule == "title_fuzzy_same_year"
    assert group.score >= 92
    assert group.member_indices == [0, 1]
    assert articles[0].duplicate_group_id == articles[1].duplicate_group_id
    assert articles[0].is_duplicate is False
    assert articles[1].is_duplicate is True
    assert articles[2].duplicate_group_id is None
    assert articles[2].is_duplicate is False
