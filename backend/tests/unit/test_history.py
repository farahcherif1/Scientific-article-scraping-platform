import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, CollectionRun
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


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_history_empty_on_fresh_db():
    response = client.get("/api/v1/history")
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["pagination"]["total"] == 0


def test_history_returns_runs_most_recent_first():
    db = TestingSessionLocal()
    db.add(
        CollectionRun(
            keywords=["ai"],
            sources=["arXiv"],
            article_count=10,
            duplicate_count=2,
            status="completed",
        )
    )
    db.add(
        CollectionRun(
            keywords=["ml"],
            sources=["OpenAlex"],
            article_count=5,
            duplicate_count=0,
            status="failed",
        )
    )
    db.commit()
    db.close()

    response = client.get("/api/v1/history")
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["data"][0]["keywords"] == ["ml"]
    assert body["data"][0]["status"] == "failed"
    assert body["data"][0]["id"].startswith("COL-")
    assert body["pagination"]["total"] == 2
