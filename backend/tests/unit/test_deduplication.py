from datetime import UTC, datetime
from app.domain.cleaning import normalize_articles
from app.domain.deduplication import deduplicate_articles, filter_for_export
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


def test_title_exact_authors_similar_groups_without_matching_year():
    articles = normalize_articles(
        [
            _raw(title="Neural Networks Explained", authors=["John Smith", "Jane Doe"], year=2018),
            _raw(title="Neural Networks Explained", authors=["Jane Doe", "John Smith"], year=2021),
        ]
    )
    result = deduplicate_articles(articles)

    assert result.duplicate_count == 1
    assert result.groups[0].rule == "title_exact_authors_similar"
    assert articles[0].is_duplicate is False
    assert articles[1].is_duplicate is True


def test_transitive_grouping_via_doi_and_fuzzy_title_chain():
    articles = normalize_articles(
        [
            _raw(title="Paper Alpha", doi="10.1/shared", year=2019),
            _raw(title="Paper Alpha Variant", doi="10.1/shared", year=2019),
            _raw(title="Paper Alpha Varient", doi=None, year=2019),  # typo, fuzzy-matches #1
        ]
    )
    result = deduplicate_articles(articles)

    group_ids = {a.duplicate_group_id for a in articles}
    assert len(group_ids) == 1
    assert result.duplicate_count == 2
    assert len(result.groups) == 1
    assert result.groups[0].member_indices == [0, 1, 2]


def test_canonical_is_lowest_original_index():
    articles = normalize_articles(
        [
            _raw(title="Original Paper", doi="10.1/x"),
            _raw(title="Original Paper Copy", doi="10.1/x"),
        ]
    )
    result = deduplicate_articles(articles)

    assert result.groups[0].canonical_index == 0
    assert articles[0].is_duplicate is False
    assert articles[1].is_duplicate is True


def test_unrelated_articles_are_not_grouped():
    articles = normalize_articles(
        [
            _raw(title="Quantum Computing Basics", year=2020, doi="10.1/a"),
            _raw(title="Culinary Arts of France", year=2020, doi="10.1/b"),
        ]
    )
    result = deduplicate_articles(articles)

    assert result.duplicate_count == 0
    assert len(result.groups) == 0
    assert articles[0].duplicate_group_id is None
    assert articles[1].duplicate_group_id is None


def test_report_duplicate_count_matches_non_canonical_members_across_groups():
    articles = normalize_articles(
        [
            _raw(title="Group A", doi="10.1/a"),
            _raw(title="Group A Copy", doi="10.1/a"),
            _raw(title="Group A Copy Two", doi="10.1/a"),
            _raw(title="Group B", doi="10.1/b"),
            _raw(title="Group B Copy", doi="10.1/b"),
        ]
    )
    result = deduplicate_articles(articles)

    # 5 total, 2 groups (3-member + 2-member) -> 2 + 1 = 3 non-canonical duplicates
    assert result.duplicate_count == 3
    assert len(result.groups) == 2


def test_empty_input_returns_empty_result():
    result = deduplicate_articles([])

    assert result.articles == []
    assert result.duplicate_count == 0
    assert result.groups == []


def test_single_article_has_no_duplicate_group():
    articles = normalize_articles([_raw(title="Solo Paper")])
    result = deduplicate_articles(articles)

    assert articles[0].duplicate_group_id is None
    assert articles[0].is_duplicate is False
    assert result.duplicate_count == 0


def test_missing_titles_do_not_crash_or_falsely_match():
    articles = normalize_articles(
        [
            _raw(title="   ", year=2020, doi=None),
            _raw(title="   ", year=2020, doi=None),
        ]
    )
    result = deduplicate_articles(articles)

    assert result.duplicate_count == 0
    assert articles[0].duplicate_group_id is None


def test_filter_for_export_keeps_all_when_exclude_duplicates_false():
    articles = normalize_articles(
        [
            _raw(title="Paper A", doi="10.1/x"),
            _raw(title="Paper A Copy", doi="10.1/x"),
        ]
    )
    deduplicate_articles(articles)
    filtered = filter_for_export(articles, exclude_duplicates=False)

    assert len(filtered) == 2


def test_filter_for_export_removes_non_canonical_when_true():
    articles = normalize_articles(
        [
            _raw(title="Paper A", doi="10.1/x"),
            _raw(title="Paper A Copy", doi="10.1/x"),
            _raw(title="Unrelated Paper", doi="10.1/z"),
        ]
    )
    deduplicate_articles(articles)
    filtered = filter_for_export(articles, exclude_duplicates=True)

    assert len(filtered) == 2
    assert all(not a.is_duplicate for a in filtered)


def test_filter_for_export_does_not_mutate_marking():
    articles = normalize_articles(
        [
            _raw(title="Paper A", doi="10.1/x"),
            _raw(title="Paper A Copy", doi="10.1/x"),
        ]
    )
    deduplicate_articles(articles)
    filter_for_export(articles, exclude_duplicates=True)

    # marking survives even though export filtered it out - never deleted internally
    assert articles[1].duplicate_group_id is not None
    assert articles[1].is_duplicate is True
