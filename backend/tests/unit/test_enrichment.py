from app.domain.enrichment import KeywordPhrase, extract_keywords, merge_keywords


def test_extract_keywords_returns_phrase_scores_without_stop_words():
    text = (
        "The rapid development of machine learning and deep learning models "
        "improves classification and prediction in healthcare systems."
    )

    result = extract_keywords(text)

    assert 3 <= len(result) <= 7
    assert all(isinstance(item, KeywordPhrase) for item in result)
    assert all(item.score >= 0 for item in result)
    assert all("the" not in item.phrase.lower() for item in result)
    assert all("and" not in item.phrase.lower() for item in result)
    assert any("machine" in item.phrase.lower() or "learning" in item.phrase.lower() for item in result)


def test_merge_keywords_keeps_author_keywords_and_stores_auto_keywords_separately():
    existing_keywords, auto_keywords = merge_keywords(
        ["neural network"],
        "Deep learning models use neural networks for classification and prediction.",
    )

    assert existing_keywords == ["neural network"]
    assert 3 <= len(auto_keywords) <= 7
    assert all(isinstance(item, KeywordPhrase) for item in auto_keywords)
