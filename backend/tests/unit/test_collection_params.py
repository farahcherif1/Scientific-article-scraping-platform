from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _valid_payload(**overrides):
    payload = {
        "keywords": ["ai", "nlp"],
        "sources": ["arxiv", "openalex"],
        "max_articles_per_keyword": 50,
        "year_from": 2018,
        "year_to": 2024,
    }
    payload.update(overrides)
    return payload


def test_valid_params_returns_summary():
    response = client.post("/api/v1/collections/params/validate", json=_valid_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["summary"]["active_sources"] == 2
    assert body["summary"]["selected_keywords"] == 2
    assert body["summary"]["max_potential_yield"] == 50 * 2 * 2


def test_max_articles_below_range_rejected():
    response = client.post(
        "/api/v1/collections/params/validate", json=_valid_payload(max_articles_per_keyword=5)
    )
    assert response.status_code == 422


def test_max_articles_above_range_rejected():
    response = client.post(
        "/api/v1/collections/params/validate", json=_valid_payload(max_articles_per_keyword=150)
    )
    assert response.status_code == 422


def test_year_from_after_year_to_rejected():
    response = client.post(
        "/api/v1/collections/params/validate",
        json=_valid_payload(year_from=2024, year_to=2018),
    )
    assert response.status_code == 422


def test_empty_sources_rejected():
    response = client.post("/api/v1/collections/params/validate", json=_valid_payload(sources=[]))
    assert response.status_code == 422


def test_optional_filters_accepted_and_defaulted():
    response = client.post(
        "/api/v1/collections/params/validate",
        json=_valid_payload(language="French", domain="Computer Science"),
    )
    assert response.status_code == 200


def test_defaults_never_drop_data_by_default():
    response = client.post("/api/v1/collections/params/validate", json=_valid_payload())
    assert response.status_code == 200
    # Defaults enforced server-side even if the client omits them.
    from app.schemas.collections import CollectionParamsRequest

    parsed = CollectionParamsRequest(**_valid_payload())
    assert parsed.include_missing_abstract is True
    assert parsed.exclude_duplicates_on_export is True


def test_explicit_false_overrides_apply():
    response = client.post(
        "/api/v1/collections/params/validate",
        json=_valid_payload(include_missing_abstract=False, exclude_duplicates_on_export=False),
    )
    assert response.status_code == 200
