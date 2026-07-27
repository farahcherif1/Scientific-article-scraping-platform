from datetime import UTC, datetime

from app.domain.cleaning import (
    build_missing_value_report,
    normalize_abstract,
    normalize_article,
    normalize_articles,
    normalize_author_name,
    normalize_authors,
    normalize_doi,
    normalize_title,
    normalize_year,
)
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


# ---------------------------------------------------------------------------
# T-04.1.1 - title normalization
# ---------------------------------------------------------------------------


def test_title_unescapes_html_entities():
    assert normalize_title("Robots &amp; Rules") == "Robots & Rules"


def test_title_unescaped_entities_that_form_tags_are_still_stripped():
    # &lt;i&gt; unescapes to <i>, which must then be stripped as markup too
    assert normalize_title("&lt;i&gt;Robust&lt;/i&gt; Learning") == "Robust Learning"


def test_title_strips_html_tags():
    assert normalize_title("<i>Robust</i> <b>Learning</b>") == "Robust Learning"


def test_title_strips_latex_macros_with_braces():
    assert normalize_title(r"\textbf{Robust} \emph{Learning}") == "Robust Learning"


def test_title_strips_nested_latex_macros():
    assert normalize_title(r"\textbf{\emph{Robust Learning}}") == "Robust Learning"


def test_title_strips_bare_latex_math_and_commands():
    # bare (brace-less) commands like \alpha are LaTeX symbol macros, not
    # literal text, so they're dropped entirely rather than left as "alpha"
    result = normalize_title(r"A Study of $\alpha$-Convergence \& Growth")
    assert result == "A Study of -Convergence & Growth"
    assert "$" not in result
    assert "\\" not in result


def test_title_collapses_multiple_whitespace():
    assert normalize_title("Deep    Learning\n\tfor   NLP") == "Deep Learning for NLP"


def test_title_is_capped_at_512_chars():
    long_title = "Word " * 200  # far over 512 chars once joined
    result = normalize_title(long_title)
    assert len(result) <= 512
    assert not result.endswith(" ")


def test_title_has_no_leftover_markup():
    result = normalize_title(r"<b>\textbf{Deep &amp; Wide}</b> Learning")
    assert "<" not in result
    assert ">" not in result
    assert "\\" not in result
    assert "{" not in result and "}" not in result


def test_title_none_or_empty_becomes_empty_string():
    assert normalize_title(None) == ""
    assert normalize_title("") == ""
    assert normalize_title("   ") == ""


# ---------------------------------------------------------------------------
# T-04.1.2 - author normalization
# ---------------------------------------------------------------------------


def test_author_first_last_passthrough():
    assert normalize_author_name("John Smith") == "John Smith"


def test_author_last_comma_first_is_reordered():
    assert normalize_author_name("Smith, John") == "John Smith"


def test_author_all_caps_is_title_cased():
    assert normalize_author_name("JOHN SMITH") == "John Smith"


def test_author_all_caps_with_comma_is_reordered_and_cased():
    assert normalize_author_name("SMITH, JOHN") == "John Smith"


def test_author_collapses_internal_whitespace():
    assert normalize_author_name("John   Smith") == "John Smith"


def test_author_empty_or_whitespace_only_is_dropped():
    assert normalize_author_name("") is None
    assert normalize_author_name("   ") is None


def test_normalize_authors_filters_empties_and_normalizes_each():
    result = normalize_authors(["Smith, John", "JANE DOE", "", "  ", "Bob Lee"])
    assert result == ["John Smith", "Jane Doe", "Bob Lee"]


def test_normalize_authors_empty_list_stays_empty():
    assert normalize_authors([]) == []


# ---------------------------------------------------------------------------
# T-04.1.3 - year + DOI normalization
# ---------------------------------------------------------------------------


def test_year_valid_passthrough():
    assert normalize_year(2021) == 2021


def test_year_none_stays_none():
    assert normalize_year(None) is None


def test_year_implausibly_old_becomes_none():
    assert normalize_year(150) is None


def test_year_implausibly_future_becomes_none():
    assert normalize_year(9999) is None


def test_doi_strips_https_prefix_and_lowercases():
    assert normalize_doi("https://doi.org/10.1234/ABCD") == "10.1234/abcd"


def test_doi_strips_http_prefix():
    assert normalize_doi("http://doi.org/10.1234/ABCD") == "10.1234/abcd"


def test_doi_strips_bare_doi_colon_prefix():
    assert normalize_doi("doi:10.1234/ABCD") == "10.1234/abcd"


def test_doi_prefix_match_is_case_insensitive():
    assert normalize_doi("HTTPS://DOI.ORG/10.1234/ABCD") == "10.1234/abcd"


def test_doi_without_prefix_is_just_lowercased():
    assert normalize_doi("10.1234/ABCD") == "10.1234/abcd"


def test_doi_none_or_empty_stays_none():
    assert normalize_doi(None) is None
    assert normalize_doi("") is None
    assert normalize_doi("   ") is None


# ---------------------------------------------------------------------------
# T-04.1.4 - abstract cleaning
# ---------------------------------------------------------------------------


def test_abstract_cleans_markup_like_title():
    result = normalize_abstract(r"<p>\textbf{Background}: multiple   spaces &amp; tags</p>")
    assert result == "Background: multiple spaces & tags"


def test_abstract_has_no_length_cap():
    long_abstract = "Word " * 200
    result = normalize_abstract(long_abstract)
    assert result is not None
    assert len(result) > 512


def test_abstract_none_or_empty_becomes_none():
    assert normalize_abstract(None) is None
    assert normalize_abstract("") is None
    assert normalize_abstract("   ") is None


# ---------------------------------------------------------------------------
# T-04.1.5 - missing fields are flagged, never dropped
# ---------------------------------------------------------------------------


def test_normalize_article_full_record_has_no_missing_fields():
    raw = _raw(
        title="A Great Paper",
        authors=["Smith, John"],
        year=2020,
        abstract="An abstract.",
        doi="https://doi.org/10.1/X",
        url="https://example.com",
        venue="ICML",
        domain="cs.LG",
    )

    clean = normalize_article(raw)

    assert clean.title == "A Great Paper"
    assert clean.authors == ["John Smith"]
    assert clean.year == 2020
    assert clean.doi == "10.1/x"
    assert clean.missing_fields == []


def test_normalize_article_missing_fields_are_null_not_dropped():
    raw = _raw(title="Only A Title")

    clean = normalize_article(raw)

    assert clean.title == "Only A Title"
    assert clean.authors == []
    assert clean.year is None
    assert clean.abstract is None
    assert clean.doi is None
    assert clean.url is None
    assert clean.venue is None
    assert clean.domain is None
    # every optional field that ended up empty is flagged, and the article
    # itself survives (i.e. is returned) rather than being discarded
    assert set(clean.missing_fields) == {
        "authors",
        "year",
        "abstract",
        "doi",
        "url",
        "venue",
        "domain",
    }


def test_normalize_article_empty_title_is_flagged_too():
    raw = _raw(title="   ")

    clean = normalize_article(raw)

    assert clean.title == ""
    assert "title" in clean.missing_fields


def test_normalize_article_preserves_source_keyword_and_collection_date():
    raw = _raw(source=SourceEnum.OPENALEX, search_keyword="nlp")

    clean = normalize_article(raw)

    assert clean.source == SourceEnum.OPENALEX
    assert clean.search_keyword == "nlp"
    assert clean.collection_date == COLLECTED_AT


def test_normalize_articles_maps_a_batch():
    raws = [_raw(title=f"Paper {i}") for i in range(3)]

    result = normalize_articles(raws)

    assert [a.title for a in result] == ["Paper 0", "Paper 1", "Paper 2"]


def test_missing_value_report_counts_and_percentages():
    articles = normalize_articles(
        [
            _raw(title="Complete", authors=["John Smith"], year=2020, abstract="x", doi="10.1/x"),
            _raw(title="No DOI", authors=["John Smith"], year=2020, abstract="x", doi=None),
            _raw(title="No DOI or year", authors=["John Smith"], year=None, abstract="x", doi=None),
        ]
    )

    report = build_missing_value_report(articles)

    assert report.total_articles == 3
    assert report.missing_counts["doi"] == 2
    assert report.missing_counts["year"] == 1
    assert "authors" not in report.missing_counts
    assert report.missing_percentages["doi"] == round(2 / 3 * 100, 2)
    assert report.missing_percentages["year"] == round(1 / 3 * 100, 2)


def test_missing_value_report_empty_batch_has_zero_total_and_no_division_error():
    report = build_missing_value_report([])

    assert report.total_articles == 0
    assert report.missing_counts == {}
    assert report.missing_percentages == {}
