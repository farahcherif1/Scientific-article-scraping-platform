from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Article, Base, CollectionRun
from app.db.session import get_db
from app.main import app

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_db():
    # Scoped per-test (not a module-level assignment) so this doesn't clobber
    # other test modules' own `app.dependency_overrides[get_db]` when several
    # are collected in the same pytest session (see test_start_collection.py).
    previous_override = app.dependency_overrides.get(get_db)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        if previous_override is not None:
            app.dependency_overrides[get_db] = previous_override
        else:
            app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=engine)


def _make_run(db, keywords=None, sources=None) -> CollectionRun:
    run = CollectionRun(
        keywords=keywords or ["ai"],
        sources=sources or ["arxiv"],
        status="completed",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _make_article(db, run_id: int, **overrides) -> Article:
    defaults = {
        "collection_run_id": run_id,
        "title": "Sample Article",
        "authors": ["Jane Doe"],
        "year": 2020,
        "abstract": "An abstract.",
        "url": "https://example.org/a",
        "doi": "10.1/abc",
        "venue": "Venue",
        "domain": "cs",
        "categories": ["cs.AI"],
        "citation_count": 5,
        "source": "arxiv",
        "search_keyword": "ai",
        "collection_date": datetime.now(UTC),
        "duplicate_group_id": None,
        "duplicate_similarity_score": None,
        "duplicate_rule": None,
        "is_duplicate": False,
        "missing_fields": [],
        "relevance_score": 1,
    }
    defaults.update(overrides)
    article = Article(**defaults)
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


def _seed_db():
    db = TestingSessionLocal()
    run = _make_run(db)
    other_run = _make_run(db)
    for i in range(3):
        _make_article(
            db,
            run.id,
            title=f"Article {i}",
            year=2018 + i,
            citation_count=i * 10,
            relevance_score=i,
            source="arxiv" if i % 2 == 0 else "openalex",
        )
    _make_article(db, run.id, title="Duplicate", is_duplicate=True, duplicate_group_id="DUP-001")
    _make_article(db, run.id, title="No DOI", doi=None)
    _make_article(db, run.id, title="No Abstract", abstract=None)
    _make_article(db, other_run.id, title="Other run's article")
    public_id, other_public_id = run.public_id, other_run.public_id
    db.close()
    return public_id, other_public_id


def test_articles_unknown_collection_returns_404():
    response = client.get("/api/v1/collections/COL-9999/articles")
    assert response.status_code == 404


def test_articles_malformed_collection_id_returns_404():
    response = client.get("/api/v1/collections/not-an-id/articles")
    assert response.status_code == 404


def test_articles_returns_envelope_shape():
    run_id, _ = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"data", "pagination", "sort", "filters"}
    assert set(body["pagination"].keys()) == {"total", "page", "page_size"}


def test_articles_default_excludes_duplicates():
    run_id, _ = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles")
    titles = [a["title"] for a in response.json()["data"]]
    assert "Duplicate" not in titles


def test_articles_only_returns_this_run():
    run_id, other_run_id = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles")
    titles = [a["title"] for a in response.json()["data"]]
    assert "Other run's article" not in titles


def test_articles_pagination():
    run_id, _ = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles?page=1&page_size=2")
    body = response.json()
    assert len(body["data"]) == 2
    assert body["pagination"]["total"] == 5  # 6 seeded minus 1 duplicate
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["page_size"] == 2


def test_articles_sort_by_year_ascending():
    run_id, _ = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles?sort=year&page_size=50")
    years = [a["year"] for a in response.json()["data"] if a["year"] is not None]
    assert years == sorted(years)


def test_articles_sort_by_year_descending():
    run_id, _ = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles?sort=-year&page_size=50")
    years = [a["year"] for a in response.json()["data"] if a["year"] is not None]
    assert years == sorted(years, reverse=True)


def test_articles_sort_by_citation_count():
    run_id, _ = _seed_db()
    response = client.get(
        f"/api/v1/collections/{run_id}/articles?sort=-citation_count&page_size=50"
    )
    counts = [a["citation_count"] for a in response.json()["data"]]
    assert counts == sorted(counts, reverse=True)


def test_articles_default_sort_is_relevance_descending():
    run_id, _ = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles?page_size=50")
    scores = [a["relevance_score"] for a in response.json()["data"]]
    assert scores == sorted(scores, reverse=True)
    assert response.json()["sort"] == "-relevance"


def test_articles_filter_by_year_from_and_to():
    run_id, _ = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles?year_from=2019&year_to=2019")
    assert all(a["year"] == 2019 for a in response.json()["data"])
    assert len(response.json()["data"]) == 1


def test_articles_filter_by_year_from_only():
    run_id, _ = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles?year_from=2019")
    years = [a["year"] for a in response.json()["data"] if a["year"] is not None]
    assert years and all(y >= 2019 for y in years)


def test_articles_filter_by_year_to_only():
    run_id, _ = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles?year_to=2018")
    years = [a["year"] for a in response.json()["data"] if a["year"] is not None]
    assert years and all(y <= 2018 for y in years)


def test_articles_year_range_excludes_undated_articles():
    run_id, _ = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles?year_from=1900")
    titles = [a["title"] for a in response.json()["data"]]
    assert "Sample Article" not in titles or all(
        a["year"] is not None for a in response.json()["data"]
    )


def test_articles_invalid_year_range_returns_422():
    run_id, _ = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles?year_from=2022&year_to=2018")
    assert response.status_code == 422


def test_articles_filter_by_single_source():
    run_id, _ = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles?source=openalex")
    assert all(a["source"] == "openalex" for a in response.json()["data"])
    assert len(response.json()["data"]) >= 1


def test_articles_filter_by_multiple_sources():
    run_id, _ = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles?source=openalex&source=arxiv")
    sources = {a["source"] for a in response.json()["data"]}
    assert sources <= {"openalex", "arxiv"}
    assert len(response.json()["data"]) >= 2


def test_articles_filter_has_doi_false():
    run_id, _ = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles?has_doi=false")
    titles = [a["title"] for a in response.json()["data"]]
    assert titles == ["No DOI"]


def test_articles_filter_has_abstract_false():
    run_id, _ = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles?has_abstract=false")
    titles = [a["title"] for a in response.json()["data"]]
    assert titles == ["No Abstract"]


def test_articles_filter_by_keyword_substring_case_insensitive():
    db = TestingSessionLocal()
    run = _make_run(db)
    _make_article(db, run.id, title="Match", search_keyword="Neural Networks")
    _make_article(db, run.id, title="No Match", search_keyword="genomics")
    public_id = run.public_id
    db.close()

    response = client.get(f"/api/v1/collections/{public_id}/articles?keyword=neural")
    titles = [a["title"] for a in response.json()["data"]]
    assert titles == ["Match"]


def test_articles_filters_combine_with_and():
    run_id, _ = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles?source=arxiv&has_doi=false")
    data = response.json()["data"]
    assert all(a["source"] == "arxiv" and a["doi"] is None for a in data)


def test_articles_keyword_over_max_length_returns_422():
    run_id, _ = _seed_db()
    response = client.get(f"/api/v1/collections/{run_id}/articles?keyword={'a' * 201}")
    assert response.status_code == 422


def test_articles_too_many_source_filters_returns_422():
    run_id, _ = _seed_db()
    query = "&".join(f"source=s{i}" for i in range(51))
    response = client.get(f"/api/v1/collections/{run_id}/articles?{query}")
    assert response.status_code == 422


def test_articles_empty_result_for_run_with_no_articles():
    db = TestingSessionLocal()
    run = _make_run(db)
    public_id = run.public_id
    db.close()
    response = client.get(f"/api/v1/collections/{public_id}/articles")
    body = response.json()
    assert body["data"] == []
    assert body["pagination"]["total"] == 0
