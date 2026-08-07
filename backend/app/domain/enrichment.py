"""Keyword enrichment helpers for article records.

This module provides a lightweight TF-IDF based extractor for article
abstracts, along with a merge helper that preserves author-supplied keywords
while storing auto-extracted phrases separately in ``keywords_auto``.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from html import unescape

from sklearn.feature_extraction.text import TfidfVectorizer

from app.domain.cleaning import clean_keywords

_ENGLISH_STOP_WORDS = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "doing",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "just",
    "me",
    "more",
    "most",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "now",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "with",
    "would",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
}

_FRENCH_STOP_WORDS = {
    "ai",
    "aussi",
    "autre",
    "aux",
    "avec",
    "ce",
    "ces",
    "cette",
    "dan",
    "de",
    "des",
    "du",
    "elle",
    "en",
    "et",
    "être",
    "fait",
    "ils",
    "je",
    "la",
    "le",
    "les",
    "leur",
    "lui",
    "ma",
    "mais",
    "me",
    "même",
    "mes",
    "moins",
    "notre",
    "nous",
    "on",
    "ou",
    "où",
    "par",
    "pas",
    "plus",
    "pour",
    "que",
    "qui",
    "sa",
    "sans",
    "ses",
    "son",
    "sont",
    "sous",
    "sur",
    "ta",
    "te",
    "tes",
    "toi",
    "ton",
    "tu",
    "un",
    "une",
    "vos",
    "votre",
    "vous",
    "y",
}

_STOP_WORDS = _ENGLISH_STOP_WORDS | _FRENCH_STOP_WORDS


def _normalize_stop_words(stop_words: set[str]) -> set[str]:
    normalized: set[str] = set()
    for word in stop_words:
        ascii_token = unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode("ascii")
        normalized.add(ascii_token)
    return normalized


_NORMALIZED_STOP_WORDS = _normalize_stop_words(_STOP_WORDS)
_GENERIC_TERMS = {
    "method",
    "methods",
    "study",
    "studies",
    "approach",
    "approaches",
    "analysis",
    "results",
    "result",
    "paper",
    "papers",
    "research",
    "work",
    "based",
    "using",
    "use",
    "used",
    "new",
    "improve",
    "improves",
    "improved",
    "develop",
    "developed",
    "development",
    "data",
    "information",
}


@dataclass(frozen=True)
class KeywordPhrase:
    phrase: str
    score: float


def _normalize_text(text: str | None) -> str:
    if not text:
        return ""
    cleaned = unescape(text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def extract_keywords(text: str | None, *, max_keywords: int = 7) -> list[KeywordPhrase]:
    """Extract 3-7 keyword phrases from a text using TF-IDF.

    The extractor uses a single-document TF-IDF vectorizer over English and
    French stop-words, with unigrams and bigrams, and returns the top-scoring
    phrases with their scores.
    """
    normalized = _normalize_text(text)
    if not normalized:
        return []

    vectorizer = TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        stop_words=sorted(_NORMALIZED_STOP_WORDS),
        ngram_range=(1, 2),
        min_df=1,
        max_features=50,
    )
    matrix = vectorizer.fit_transform([normalized])
    feature_names = vectorizer.get_feature_names_out()
    scores = matrix.toarray()[0]

    ranked: list[tuple[float, str]] = []
    for feature_name, score in zip(feature_names, scores):
        if score <= 0:
            continue
        feature_name = feature_name.strip()
        if not feature_name or len(feature_name) <= 1:
            continue
        tokenized = feature_name.split()
        if any(token in _GENERIC_TERMS for token in tokenized):
            continue
        if any(token in _NORMALIZED_STOP_WORDS for token in tokenized):
            continue
        ranked.append((float(score), feature_name))

    ranked.sort(key=lambda item: item[0], reverse=True)

    if not ranked:
        return []

    phrases = [
        KeywordPhrase(phrase=feature_name, score=round(score, 4))
        for score, feature_name in ranked[:max_keywords]
    ]

    if len(phrases) < 3:
        fallback_terms = [
            term for _, term in ranked[:3] if term and len(term.split()) <= 2 and term.lower() not in _NORMALIZED_STOP_WORDS
        ]
        if fallback_terms:
            return [
                KeywordPhrase(phrase=term, score=round(score, 4))
                for score, term in sorted(
                    [(score, term) for score, term in ranked if term in fallback_terms],
                    key=lambda item: item[0],
                    reverse=True,
                )[:3]
            ]
        return [
            KeywordPhrase(phrase=feature_name, score=round(score, 4))
            for score, feature_name in ranked[:3]
        ]

    return phrases


def merge_keywords(author_keywords: list[str] | None, abstract: str | None) -> tuple[list[str], list[KeywordPhrase]]:
    """Merge author-supplied keywords with auto-extracted ones.

    Existing keywords are preserved and cleaned; auto-extracted keywords are
    stored separately in the returned ``keywords_auto`` list.
    """
    preserved_keywords = clean_keywords(author_keywords or [])
    if not abstract:
        return preserved_keywords, []

    auto_keywords = extract_keywords(abstract)
    return preserved_keywords, auto_keywords
