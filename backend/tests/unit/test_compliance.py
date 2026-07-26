from datetime import UTC, datetime
import pytest

from app.domain.compliance import enforce_max_articles_per_keyword
from app.domain.entities import RawArticle, SourceEnum


def _article(source: SourceEnum, keyword: str, title: str) -> RawArticle:
    return RawArticle(
        title=title,
        source=source,
        search_keyword=keyword,
        collection_date=datetime.now(UTC),
    )


def test_group_under_cap_is_untouched():
    articles = [_article(SourceEnum.ARXIV, "ai", f"paper {i}") for i in range(3)]

    result = enforce_max_articles_per_keyword(articles, max_articles_per_keyword=5)

    assert len(result.articles) == 3
    assert result.capped_groups == []
    assert result.cap_was_hit is False


def test_group_over_cap_is_truncated_and_flagged():
    articles = [_article(SourceEnum.ARXIV, "ai", f"paper {i}") for i in range(7)]

    result = enforce_max_articles_per_keyword(articles, max_articles_per_keyword=5)

    assert len(result.articles) == 5
    assert [a.title for a in result.articles] == [f"paper {i}" for i in range(5)]
    assert result.capped_groups == [(SourceEnum.ARXIV, "ai")]
    assert result.cap_was_hit is True


def test_groups_are_independent_per_source_and_keyword():
    articles = (
        [_article(SourceEnum.ARXIV, "ai", f"arxiv-ai-{i}") for i in range(6)]
        + [_article(SourceEnum.OPENALEX, "ai", f"openalex-ai-{i}") for i in range(2)]
        + [_article(SourceEnum.ARXIV, "nlp", f"arxiv-nlp-{i}") for i in range(1)]
    )

    result = enforce_max_articles_per_keyword(articles, max_articles_per_keyword=5)

    assert len(result.articles) == 5 + 2 + 1
    assert result.capped_groups == [(SourceEnum.ARXIV, "ai")]


def test_empty_input_returns_empty_result():
    result = enforce_max_articles_per_keyword([], max_articles_per_keyword=10)

    assert result.articles == []
    assert result.cap_was_hit is False


def test_rejects_non_positive_cap():
    with pytest.raises(ValueError):
        enforce_max_articles_per_keyword([], max_articles_per_keyword=0)
