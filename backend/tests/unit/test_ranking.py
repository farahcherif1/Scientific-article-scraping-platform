from app.domain.ranking import compute_relevance_score


def test_counts_hits_across_title_and_abstract():
    score = compute_relevance_score(
        "Machine Learning for Genomics",
        "This paper applies machine learning techniques to genomics data.",
        ["machine learning", "genomics"],
    )
    # title: "machine learning" x1, "genomics" x1
    # abstract: "machine learning" x1, "genomics" x1
    assert score == 4


def test_is_case_insensitive():
    score = compute_relevance_score("AI in Healthcare", None, ["ai"])
    assert score == 1


def test_matches_on_word_boundaries_not_substrings():
    score = compute_relevance_score("A comfortable chair", None, ["ai"])
    assert score == 0


def test_no_matches_returns_zero():
    score = compute_relevance_score("Quantum Computing", "Abstract text.", ["biology"])
    assert score == 0


def test_handles_missing_abstract():
    score = compute_relevance_score("Deep Learning Basics", None, ["deep learning"])
    assert score == 1


def test_handles_empty_keyword_list():
    score = compute_relevance_score("Deep Learning Basics", "Abstract.", [])
    assert score == 0


def test_ignores_blank_keywords():
    score = compute_relevance_score("Deep Learning Basics", None, ["  ", "learning"])
    assert score == 1
