"""
Custom connector persistence (CRUD API) + registry integration
(EP-custom-connectors): proves a saved, enabled custom connector reaches the
orchestrator's connector_factories dict exactly like a built-in source, with
no special-casing in `app/orchestrator/runner.py` needed for that to work -
mirrors the spirit of test_connector_factories_wiring.py, but for
DB-persisted custom connectors instead of the five hardcoded ones.
"""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.connectors.generic import GenericConnector
from app.connectors.registry import load_custom_connector_factories
from app.db.models import Base, CustomConnector
from app.db.session import get_db
from app.main import app
from app.orchestrator import state as state_store
from app.use_cases import start_collection as start_collection_module
from app.use_cases.manage_custom_connectors import generate_unique_slug, slugify

engine = create_engine(
    "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
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


@pytest.fixture(autouse=True)
def _resolve_placeholder_hostnames_to_a_public_ip(monkeypatch):
    """
    These tests exercise the real endpoints end-to-end, so requests go
    through the real SSRF guard (`default_host_guard`), DNS resolution
    included - unlike test_generic_connector.py, which injects a no-op guard
    directly. `api.example.org` has no real DNS record, so resolve it (and
    anything else) to a public IP here rather than depending on real
    network access in a unit test.
    """
    monkeypatch.setattr(
        "socket.getaddrinfo", lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))]
    )


def _valid_config(**overrides) -> dict:
    config = {
        "base_url": "https://api.example.org/search",
        "query_mapping": {"keyword_param": "q"},
        "pagination": {"style": "none", "results_path": "items"},
        "field_mapping": {"title": {"path": "title"}},
    }
    config.update(overrides)
    return config


def _create_payload(name="IEEE Xplore", **config_overrides) -> dict:
    return {"name": name, "config": _valid_config(**config_overrides), "enabled": True}


# ---------------------------------------------------------------------------
# Slug generation (pure)
# ---------------------------------------------------------------------------


def test_slugify_lowercases_and_replaces_punctuation():
    assert slugify("IEEE Xplore!") == "ieee_xplore"


def test_slugify_falls_back_to_custom_for_empty_input():
    assert slugify("!!!") == "custom"


def test_generate_unique_slug_avoids_builtin_source_ids():
    with TestingSessionLocal() as db:
        slug = generate_unique_slug(db, "arxiv")
    assert slug != "arxiv"
    assert slug == "arxiv-2"


# ---------------------------------------------------------------------------
# CRUD API
# ---------------------------------------------------------------------------


def test_create_connector_persists_and_returns_slug():
    response = client.post("/api/v1/custom-connectors", json=_create_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "ieee_xplore"
    assert body["name"] == "IEEE Xplore"
    assert body["enabled"] is True


def test_duplicate_name_gets_a_disambiguated_slug():
    first = client.post("/api/v1/custom-connectors", json=_create_payload())
    second = client.post("/api/v1/custom-connectors", json=_create_payload())
    assert first.json()["id"] == "ieee_xplore"
    assert second.json()["id"] == "ieee_xplore-2"


def test_list_connectors_returns_created_entries():
    client.post("/api/v1/custom-connectors", json=_create_payload())
    response = client.get("/api/v1/custom-connectors")
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["id"] == "ieee_xplore"


def test_get_unknown_connector_returns_404():
    response = client.get("/api/v1/custom-connectors/does-not-exist")
    assert response.status_code == 404


def test_update_connector_changes_config_and_enabled():
    client.post("/api/v1/custom-connectors", json=_create_payload())
    response = client.put(
        "/api/v1/custom-connectors/ieee_xplore",
        json={"name": "IEEE Xplore", "config": _valid_config(rate_limit_rps=5), "enabled": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["config"]["rate_limit_rps"] == 5


def test_update_unknown_connector_returns_404():
    response = client.put(
        "/api/v1/custom-connectors/does-not-exist",
        json=_create_payload(),
    )
    assert response.status_code == 404


def test_delete_connector_removes_it():
    client.post("/api/v1/custom-connectors", json=_create_payload())
    delete_response = client.delete("/api/v1/custom-connectors/ieee_xplore")
    assert delete_response.status_code == 204
    assert client.get("/api/v1/custom-connectors/ieee_xplore").status_code == 404


def test_delete_unknown_connector_returns_404():
    assert client.delete("/api/v1/custom-connectors/does-not-exist").status_code == 404


def test_invalid_config_is_rejected_with_422():
    response = client.post(
        "/api/v1/custom-connectors",
        json={"name": "Bad", "config": _valid_config(base_url="not-a-url"), "enabled": True},
    )
    assert response.status_code == 422


def test_literal_private_ip_in_base_url_is_rejected_with_422():
    response = client.post(
        "/api/v1/custom-connectors",
        json={
            "name": "SSRF Attempt",
            "config": _valid_config(base_url="http://169.254.169.254/latest/meta-data/"),
            "enabled": True,
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# API key redaction (security review finding: this endpoint has no auth, so
# a stored third-party API key must never round-trip out through it)
# ---------------------------------------------------------------------------


def test_created_connector_response_never_contains_the_raw_api_key():
    response = client.post(
        "/api/v1/custom-connectors",
        json={
            "name": "IEEE Xplore",
            "config": _valid_config(
                auth={"type": "api_key_header", "key_name": "Authorization", "key_value": "Bearer super-secret"}
            ),
            "enabled": True,
        },
    )
    body = response.json()
    assert body["auth_key_configured"] is True
    assert body["config"]["auth"]["key_value"] is None
    assert "super-secret" not in response.text


def test_get_and_list_also_redact_the_key():
    client.post(
        "/api/v1/custom-connectors",
        json={
            "name": "IEEE Xplore",
            "config": _valid_config(
                auth={"type": "api_key_header", "key_name": "Authorization", "key_value": "Bearer super-secret"}
            ),
            "enabled": True,
        },
    )
    get_response = client.get("/api/v1/custom-connectors/ieee_xplore")
    list_response = client.get("/api/v1/custom-connectors")
    assert "super-secret" not in get_response.text
    assert "super-secret" not in list_response.text
    assert get_response.json()["auth_key_configured"] is True
    assert list_response.json()["data"][0]["auth_key_configured"] is True


def test_updating_with_a_blank_key_preserves_the_stored_key():
    client.post(
        "/api/v1/custom-connectors",
        json={
            "name": "IEEE Xplore",
            "config": _valid_config(
                auth={"type": "api_key_header", "key_name": "Authorization", "key_value": "Bearer super-secret"}
            ),
            "enabled": True,
        },
    )

    # Simulates the wizard round-trip: GET returns key_value=None (redacted),
    # the researcher changes an unrelated field and saves without touching
    # the key input, so PUT is sent with key_value still blank.
    update_response = client.put(
        "/api/v1/custom-connectors/ieee_xplore",
        json={
            "name": "IEEE Xplore",
            "config": _valid_config(
                rate_limit_rps=5,
                auth={"type": "api_key_header", "key_name": "Authorization", "key_value": None},
            ),
            "enabled": True,
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["config"]["rate_limit_rps"] == 5

    with TestingSessionLocal() as db:
        row = db.query(CustomConnector).filter_by(slug="ieee_xplore").first()
        assert row.config["auth"]["key_value"] == "Bearer super-secret"


def test_updating_with_a_new_key_replaces_the_stored_key():
    client.post(
        "/api/v1/custom-connectors",
        json={
            "name": "IEEE Xplore",
            "config": _valid_config(
                auth={"type": "api_key_header", "key_name": "Authorization", "key_value": "Bearer old-secret"}
            ),
            "enabled": True,
        },
    )
    client.put(
        "/api/v1/custom-connectors/ieee_xplore",
        json={
            "name": "IEEE Xplore",
            "config": _valid_config(
                auth={"type": "api_key_header", "key_name": "Authorization", "key_value": "Bearer new-secret"}
            ),
            "enabled": True,
        },
    )

    with TestingSessionLocal() as db:
        row = db.query(CustomConnector).filter_by(slug="ieee_xplore").first()
        assert row.config["auth"]["key_value"] == "Bearer new-secret"


def test_switching_auth_type_to_none_clears_the_stored_key():
    client.post(
        "/api/v1/custom-connectors",
        json={
            "name": "IEEE Xplore",
            "config": _valid_config(
                auth={"type": "api_key_header", "key_name": "Authorization", "key_value": "Bearer super-secret"}
            ),
            "enabled": True,
        },
    )
    client.put(
        "/api/v1/custom-connectors/ieee_xplore",
        json={"name": "IEEE Xplore", "config": _valid_config(auth={"type": "none"}), "enabled": True},
    )

    with TestingSessionLocal() as db:
        row = db.query(CustomConnector).filter_by(slug="ieee_xplore").first()
        assert row.config["auth"]["key_value"] is None


# ---------------------------------------------------------------------------
# Test-connection endpoint
# ---------------------------------------------------------------------------


def test_test_connection_returns_mapped_preview(httpx_mock):
    httpx_mock.add_response(json={"items": [{"title": "A Paper"}]})
    response = client.post(
        "/api/v1/custom-connectors/test",
        json={"config": _valid_config(), "keyword": "ai", "max_results": 3},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["mapped_articles"][0]["title"] == "A Paper"
    assert body["raw_response"] == {"items": [{"title": "A Paper"}]}


def test_test_connection_reports_failure_without_a_500(httpx_mock):
    for _ in range(3):
        httpx_mock.add_response(status_code=503)
    response = client.post(
        "/api/v1/custom-connectors/test",
        json={"config": _valid_config(), "keyword": "ai", "max_results": 3},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error"]


# ---------------------------------------------------------------------------
# Health-check endpoint
# ---------------------------------------------------------------------------


def test_health_endpoint_reports_healthy(httpx_mock):
    httpx_mock.add_response(json={"items": []})
    client.post("/api/v1/custom-connectors", json=_create_payload())
    response = client.get("/api/v1/custom-connectors/ieee_xplore/health")
    assert response.status_code == 200
    assert response.json() == {"id": "ieee_xplore", "healthy": True}


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


def test_registry_only_loads_enabled_connectors():
    with TestingSessionLocal() as db:
        db.add(
            CustomConnector(
                name="Enabled Source",
                slug="enabled_source",
                config=_valid_config(),
                enabled=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        db.add(
            CustomConnector(
                name="Disabled Source",
                slug="disabled_source",
                config=_valid_config(),
                enabled=False,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        db.commit()

        factories = load_custom_connector_factories(db)

    assert set(factories.keys()) == {"enabled_source"}
    assert isinstance(factories["enabled_source"](), GenericConnector)


@pytest.fixture
def _happy_path_builtin_factories(monkeypatch):
    monkeypatch.setattr(start_collection_module, "CONNECTOR_FACTORIES", {})
    monkeypatch.setattr(start_collection_module, "SESSION_FACTORY", TestingSessionLocal)
    yield
    state_store.clear_all()


def test_a_saved_custom_connector_is_reachable_through_a_real_collection_run(
    httpx_mock, _happy_path_builtin_factories
):
    """
    End-to-end: create a custom connector via the API, start a collection
    naming its slug as the only source, and confirm the orchestrator
    actually drove a GenericConnector against the mocked HTTP endpoint -
    i.e. it went through connector_factories exactly like a built-in source,
    with zero special-casing in run_collection/runner.py.
    """
    create = client.post("/api/v1/custom-connectors", json=_create_payload(name="My Source"))
    slug = create.json()["id"]

    httpx_mock.add_response(json={"items": [{"title": "Found via custom connector"}]})

    start = client.post(
        "/api/v1/collections",
        json={
            "keywords": ["ai"],
            "sources": [slug],
            "max_articles_per_keyword": 10,
        },
    )
    assert start.status_code == 202
    collection_id = start.json()["id"]

    progress = client.get(f"/api/v1/collections/{collection_id}/progress")
    body = progress.json()
    assert body["status"] == "completed"
    assert body["sources"][0]["source"] == slug
    assert body["sources"][0]["status"] == "done"
    assert body["sources"][0]["articles_fetched"] == 1
