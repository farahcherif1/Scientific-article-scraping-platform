from datetime import UTC, datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.db.session import get_db
from app.domain.entities import ConnectorError, RawArticle
from app.main import app
from app.orchestrator import state as state_store
from app.use_cases import start_collection as start_collection_module

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
    # test_history.py's own `app.dependency_overrides[get_db]` when both
    # modules are collected in the same pytest session.
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


class _FakeConnector:
    def __init__(self, source, articles_per_keyword=5, fail_keywords=None):
        self.source = source
        self.articles_per_keyword = articles_per_keyword
        self.fail_keywords = fail_keywords or set()

    async def search(self, keyword, max_results, filters=None):
        if keyword in self.fail_keywords:
            raise ConnectorError(
                source=self.source, endpoint="fake", keyword=keyword,
                error_class="Boom", message="boom",
            )
        n = min(self.articles_per_keyword, max_results)
        return [
            RawArticle(
                title=f"{self.source}-{keyword}-{i}",
                source=self.source,
                search_keyword=keyword,
                collection_date=datetime.now(UTC),
            )
            for i in range(n)
        ]

    async def aclose(self):
        pass


def _payload(**overrides):
    payload = {
        "keywords": ["ai", "nlp"],
        "sources": ["arxiv", "openalex"],
        "max_articles_per_keyword": 10,
    }
    payload.update(overrides)
    return payload


@pytest.fixture(autouse=True)
def _happy_path_connectors(monkeypatch):
    monkeypatch.setattr(
        start_collection_module,
        "CONNECTOR_FACTORIES",
        {
            "arxiv": lambda: _FakeConnector("arxiv", articles_per_keyword=5),
            "openalex": lambda: _FakeConnector("openalex", articles_per_keyword=5),
        },
    )
    monkeypatch.setattr(start_collection_module, "SESSION_FACTORY", TestingSessionLocal)
    yield
    state_store.clear_all()


def test_start_collection_returns_202_with_id():
    response = client.post("/api/v1/collections", json=_payload())
    assert response.status_code == 202
    body = response.json()
    assert body["id"].startswith("COL-")
    assert body["status"] == "running"


def test_full_run_completes_and_progress_reflects_final_state():
    start = client.post("/api/v1/collections", json=_payload())
    collection_id = start.json()["id"]

    progress = client.get(f"/api/v1/collections/{collection_id}/progress")
    assert progress.status_code == 200
    body = progress.json()
    assert body["status"] == "completed"
    assert body["overall_progress"] == 100.0
    assert {s["source"] for s in body["sources"]} == {"arxiv", "openalex"}
    assert all(s["status"] == "done" for s in body["sources"])
    assert body["error"] is None


def test_progress_for_unknown_id_returns_404():
    response = client.get("/api/v1/collections/COL-9999/progress")
    assert response.status_code == 404


def test_abort_for_unknown_id_returns_404():
    response = client.post("/api/v1/collections/COL-9999/abort")
    assert response.status_code == 404


def test_history_reflects_completed_run():
    start = client.post("/api/v1/collections", json=_payload())
    collection_id = start.json()["id"]

    history = client.get("/api/v1/history")
    assert history.status_code == 200
    matching = [item for item in history.json()["data"] if item["id"] == collection_id]
    assert len(matching) == 1
    assert matching[0]["status"] == "completed"
    assert matching[0]["article_count"] == 20  # 2 keywords x 2 sources x 5 articles


def test_run_with_a_failing_source_reports_warning_status(monkeypatch):
    monkeypatch.setattr(
        start_collection_module,
        "CONNECTOR_FACTORIES",
        {
            "arxiv": lambda: _FakeConnector("arxiv", articles_per_keyword=5, fail_keywords={"ai", "nlp"}),
            "openalex": lambda: _FakeConnector("openalex", articles_per_keyword=5),
        },
    )

    start = client.post("/api/v1/collections", json=_payload())
    collection_id = start.json()["id"]

    progress = client.get(f"/api/v1/collections/{collection_id}/progress")
    body = progress.json()
    assert body["status"] == "warning"
    assert body["warning"] is not None
    by_source = {s["source"]: s for s in body["sources"]}
    assert by_source["arxiv"]["status"] == "failed"
    assert by_source["openalex"]["status"] == "done"


def test_source_not_in_the_schema_enum_returns_422():
    response = client.post("/api/v1/collections", json=_payload(sources=["arxiv", "not_a_real_source"]))
    assert response.status_code == 422


def test_exceeding_hard_cap_returns_422_before_any_run_starts():
    response = client.post("/api/v1/collections", json=_payload(max_articles_per_keyword=150))
    assert response.status_code == 422


def test_request_with_no_sources_returns_422():
    response = client.post("/api/v1/collections", json=_payload(sources=[]))
    assert response.status_code == 422


def test_pubmed_and_semantic_scholar_are_accepted_by_the_schema():
    response = client.post(
        "/api/v1/collections",
        json=_payload(sources=["pubmed", "semantic_scholar"]),
    )
    assert response.status_code == 202
