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
    return article


def _seed_run() -> str:
    db = TestingSessionLocal()
    run = CollectionRun(keywords=["ai"], sources=["arxiv", "openalex"], status="completed")
    db.add(run)
    db.commit()
    db.refresh(run)

    # 3 unique arxiv articles: 2 with DOI, 1 without; 2 with abstract, 1 without; years 2019/2020/2020
    _make_article(db, run.id, title="A1", source="arxiv", year=2019, doi="10.1/a", abstract="x")
    _make_article(db, run.id, title="A2", source="arxiv", year=2020, doi="10.1/b", abstract=None)
    _make_article(db, run.id, title="A3", source="arxiv", year=2020, doi=None, abstract="x")
    # 1 unique openalex article
    _make_article(db, run.id, title="B1", source="openalex", year=2020, doi="10.1/c", abstract="x")
    # 2 duplicates (should be excluded from deduped stats, counted in duplicates)
    _make_article(db, run.id, title="Dup1", source="arxiv", is_duplicate=True, duplicate_group_id="DUP-001")
    _make_article(db, run.id, title="Dup2", source="arxiv", is_duplicate=True, duplicate_group_id="DUP-001")

    public_id = run.public_id
    db.close()
    return public_id


def test_stats_unknown_collection_returns_404():
    response = client.get("/api/v1/collections/COL-9999/stats")
    assert response.status_code == 404


def test_stats_totals_match_raw_data():
    run_id = _seed_run()
    response = client.get(f"/api/v1/collections/{run_id}/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 6
    assert body["deduped"] == 4
    assert body["duplicates"] == 2
    assert body["deduped"] + body["duplicates"] == body["total"]


def test_stats_percentages_computed_over_deduped_set():
    run_id = _seed_run()
    body = client.get(f"/api/v1/collections/{run_id}/stats").json()
    # 3 of 4 deduped articles have a DOI (A1, A2, B1)
    assert body["pct_with_doi"] == pytest.approx(75.0)
    # 3 of 4 deduped articles have an abstract (A1, A3, B1)
    assert body["pct_with_abstract"] == pytest.approx(75.0)


def test_stats_per_source_breakdown():
    run_id = _seed_run()
    body = client.get(f"/api/v1/collections/{run_id}/stats").json()
    by_source = {s["source"]: s for s in body["per_source"]}
    assert by_source["arxiv"]["count"] == 3
    assert by_source["openalex"]["count"] == 1


def test_stats_articles_per_year_excludes_duplicates():
    run_id = _seed_run()
    body = client.get(f"/api/v1/collections/{run_id}/stats").json()
    by_year = {entry["year"]: entry["count"] for entry in body["articles_per_year"]}
    assert by_year == {2019: 1, 2020: 3}


def test_stats_for_run_with_no_articles_is_all_zero():
    db = TestingSessionLocal()
    run = CollectionRun(keywords=["x"], sources=["arxiv"], status="completed")
    db.add(run)
    db.commit()
    db.refresh(run)
    public_id = run.public_id
    db.close()

    body = client.get(f"/api/v1/collections/{public_id}/stats").json()
    assert body["total"] == 0
    assert body["deduped"] == 0
    assert body["pct_with_doi"] == 0.0
    assert body["per_source"] == []
    assert body["articles_per_year"] == []
