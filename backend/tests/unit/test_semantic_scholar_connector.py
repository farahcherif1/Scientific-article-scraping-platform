import httpx
import pytest

from app.connectors.semantic_scholar import SemanticScholarConnector
from app.domain.entities import ConnectorError
from app.infra.cache import clear_cache


class _NoopRateLimiter:
    async def acquire(self) -> None:
        return None


def _make_connector(**overrides) -> SemanticScholarConnector:
    overrides.setdefault("rate_limiter", _NoopRateLimiter())
    return SemanticScholarConnector(**overrides)


def _make_item(
    i: int,
    doi: str | None = None,
    abstract: str | None = "An abstract.",
    fields_of_study: list[str] | None = None,
) -> dict:
    return {
        "paperId": f"paper{i}",
        "title": f"Semantic Scholar Paper {i}",
        "abstract": abstract,
        "year": 2020 + (i % 5),
        "venue": f"Conference {i}",
        "authors": [{"authorId": "a1", "name": "Ada Lovelace"}, {"authorId": "a2", "name": f"Author {i}"}],
        "externalIds": {"DOI": doi if doi is not None else f"10.5555/example.{i}"},
        "citationCount": i,
        "fieldsOfStudy": fields_of_study if fields_of_study is not None else ["Computer Science"],
        "url": f"https://www.semanticscholar.org/paper/paper{i}",
    }


def _payload(items: list[dict]) -> dict:
    return {"total": len(items), "offset": 0, "data": items}


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.mark.asyncio
async def test_search_maps_core_fields(httpx_mock):
    httpx_mock.add_response(json=_payload([_make_item(1)]))

    connector = _make_connector()
    results = await connector.search("machine learning", max_results=1)

    assert len(results) == 1
    article = results[0]
    assert article.title == "Semantic Scholar Paper 1"
    assert article.authors == ["Ada Lovelace", "Author 1"]
    assert article.year == 2021
    assert article.doi == "10.5555/example.1"
    assert article.venue == "Conference 1"
    assert article.citation_count == 1
    assert article.domain == "Computer Science"
    assert article.categories == ["Computer Science"]
    assert article.source == "semantic_scholar"


@pytest.mark.asyncio
async def test_doi_normalized_from_external_ids(httpx_mock):
    httpx_mock.add_response(
        json=_payload([_make_item(1, doi="https://doi.org/10.5555/EXAMPLE.1")])
    )

    connector = _make_connector()
    results = await connector.search("ai", max_results=1)

    assert results[0].doi == "10.5555/example.1"


@pytest.mark.asyncio
async def test_invalid_doi_normalizes_to_none(httpx_mock):
    httpx_mock.add_response(json=_payload([_make_item(1, doi="not-a-doi")]))

    connector = _make_connector()
    results = await connector.search("ai", max_results=1)

    assert results[0].doi is None


@pytest.mark.asyncio
async def test_missing_abstract_does_not_drop_record(httpx_mock):
    httpx_mock.add_response(json=_payload([_make_item(1, abstract=None)]))

    connector = _make_connector()
    results = await connector.search("ai", max_results=1)

    assert len(results) == 1
    assert results[0].abstract is None


@pytest.mark.asyncio
async def test_no_fields_of_study_leaves_domain_none(httpx_mock):
    httpx_mock.add_response(json=_payload([_make_item(1, fields_of_study=[])]))

    connector = _make_connector()
    results = await connector.search("ai", max_results=1)

    assert results[0].domain is None
    assert results[0].categories == []


@pytest.mark.asyncio
async def test_missing_authors_handled_gracefully(httpx_mock):
    sparse_item = {
        "paperId": "sparse1",
        "title": "Sparse Record",
        "externalIds": {},
    }
    httpx_mock.add_response(json=_payload([sparse_item]))

    connector = _make_connector()
    results = await connector.search("ai", max_results=1)

    assert results[0].authors == []
    assert results[0].year is None
    assert results[0].title == "Sparse Record"
    assert results[0].doi is None


@pytest.mark.asyncio
async def test_no_api_key_by_default_no_x_api_key_header(httpx_mock):
    httpx_mock.add_response(json=_payload([_make_item(1)]))

    connector = _make_connector()
    await connector.search("ai", max_results=1)

    request = httpx_mock.get_requests()[0]
    assert "x-api-key" not in request.headers


@pytest.mark.asyncio
async def test_api_key_sent_as_header_when_configured(httpx_mock):
    httpx_mock.add_response(json=_payload([_make_item(1)]))

    connector = _make_connector(api_key="secret-key")
    await connector.search("ai", max_results=1)

    request = httpx_mock.get_requests()[0]
    assert request.headers["x-api-key"] == "secret-key"


@pytest.mark.asyncio
async def test_limit_is_capped_at_100(httpx_mock):
    httpx_mock.add_response(json=_payload([_make_item(1)]))

    connector = _make_connector()
    await connector.search("ai", max_results=500)

    request = httpx_mock.get_requests()[0]
    assert request.url.params["limit"] == "100"


@pytest.mark.asyncio
async def test_network_error_raises_connector_error_after_retries(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("boom"))
    httpx_mock.add_exception(httpx.ConnectError("boom"))
    httpx_mock.add_exception(httpx.ConnectError("boom"))

    connector = _make_connector()
    with pytest.raises(ConnectorError) as exc_info:
        await connector.search("ai", max_results=5)

    assert exc_info.value.source == "semantic_scholar"
    assert len(httpx_mock.get_requests()) == 3


@pytest.mark.asyncio
async def test_non_retryable_status_raises_connector_error_immediately(httpx_mock):
    httpx_mock.add_response(status_code=404, text="Not Found")

    connector = _make_connector()
    with pytest.raises(ConnectorError):
        await connector.search("ai", max_results=5)

    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
async def test_persistent_5xx_raises_connector_error_after_max_retries(httpx_mock):
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=503)

    connector = _make_connector()
    with pytest.raises(ConnectorError):
        await connector.search("ai", max_results=5)

    assert len(httpx_mock.get_requests()) == 3


@pytest.mark.asyncio
async def test_429_retries_then_succeeds(httpx_mock):
    httpx_mock.add_response(status_code=429)
    httpx_mock.add_response(json=_payload([_make_item(1)]))

    connector = _make_connector()
    results = await connector.search("ai", max_results=1)

    assert len(results) == 1
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.asyncio
async def test_malformed_json_raises_connector_error(httpx_mock):
    httpx_mock.add_response(text="not json{{{")

    connector = _make_connector()
    with pytest.raises(ConnectorError):
        await connector.search("ai", max_results=5)


@pytest.mark.asyncio
async def test_empty_keyword_rejected():
    connector = _make_connector()
    with pytest.raises(ConnectorError):
        await connector.search("   ", max_results=5)


@pytest.mark.asyncio
async def test_max_results_below_one_rejected():
    connector = _make_connector()
    with pytest.raises(ConnectorError):
        await connector.search("ai", max_results=0)


@pytest.mark.asyncio
async def test_search_uses_the_shared_rate_limiter(httpx_mock):
    httpx_mock.add_response(json=_payload([_make_item(1)]))

    calls: list[int] = []

    class _SpyRateLimiter:
        async def acquire(self) -> None:
            calls.append(1)

    connector = SemanticScholarConnector(rate_limiter=_SpyRateLimiter())
    await connector.search("ai", max_results=1)

    assert calls == [1]


@pytest.mark.asyncio
async def test_second_identical_search_is_served_from_cache(httpx_mock):
    httpx_mock.add_response(json=_payload([_make_item(1)]))

    connector = _make_connector()
    first = await connector.search("ai", max_results=1)
    second = await connector.search("ai", max_results=1)  # no 2nd mock registered

    assert len(httpx_mock.get_requests()) == 1
    assert [a.title for a in first] == [a.title for a in second]
