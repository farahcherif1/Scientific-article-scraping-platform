import httpx
import pytest

from app.connectors.crossref import CrossrefConnector
from app.domain.entities import ConnectorError
from app.infra.cache import clear_cache


class _NoopRateLimiter:
    async def acquire(self) -> None:
        return None


def _make_connector(**overrides) -> CrossrefConnector:
    overrides.setdefault("rate_limiter", _NoopRateLimiter())
    return CrossrefConnector(**overrides)


def _make_item(i: int, doi: str | None = None, abstract: str | None = None) -> dict:
    return {
        "title": [f"Crossref Paper {i}"],
        "author": [{"given": "Ada", "family": f"Author{i}"}],
        "issued": {"date-parts": [[2020 + (i % 5)]]},
        "DOI": doi if doi is not None else f"10.1234/example.{i}",
        "publisher": "Example Publisher",
        "container-title": [f"Journal of Examples {i}"],
        "URL": f"https://doi.org/10.1234/example.{i}",
        "type": "journal-article",
        "is-referenced-by-count": i,
        "abstract": abstract,
    }


def _payload(items: list[dict]) -> dict:
    return {"message": {"items": items}}


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
    assert article.title == "Crossref Paper 1"
    assert article.authors == ["Ada Author1"]
    assert article.year == 2021
    assert article.doi == "10.1234/example.1"
    assert article.venue == "Journal of Examples 1"
    assert article.url == "https://doi.org/10.1234/example.1"
    assert article.source == "crossref"


@pytest.mark.asyncio
async def test_at_least_80_percent_have_valid_normalized_doi(httpx_mock):
    items = [_make_item(i) for i in range(8)]
    items.append(_make_item(8, doi=None))
    items.append(_make_item(9, doi="not-a-doi"))
    httpx_mock.add_response(json=_payload(items))

    connector = _make_connector()
    results = await connector.search("ai", max_results=10)

    with_doi = [a for a in results if a.doi is not None]
    assert len(with_doi) / len(results) >= 0.8
    for article in with_doi:
        assert article.doi.startswith("10.")
        assert "/" in article.doi


@pytest.mark.asyncio
async def test_doi_with_https_prefix_is_normalized(httpx_mock):
    httpx_mock.add_response(
        json=_payload([_make_item(1, doi="https://doi.org/10.1234/EXAMPLE.1")])
    )

    connector = _make_connector()
    results = await connector.search("ai", max_results=1)

    assert results[0].doi == "10.1234/example.1"


@pytest.mark.asyncio
async def test_missing_abstract_does_not_drop_record(httpx_mock):
    httpx_mock.add_response(json=_payload([_make_item(1, abstract=None)]))

    connector = _make_connector()
    results = await connector.search("ai", max_results=1)

    assert len(results) == 1
    assert results[0].abstract is None


@pytest.mark.asyncio
async def test_jats_tags_stripped_from_abstract(httpx_mock):
    httpx_mock.add_response(
        json=_payload(
            [_make_item(1, abstract="<jats:p>This is <jats:italic>great</jats:italic>.</jats:p>")]
        )
    )

    connector = _make_connector()
    results = await connector.search("ai", max_results=1)

    assert results[0].abstract == "This is great ."


@pytest.mark.asyncio
async def test_polite_pool_header_and_mailto_always_sent(httpx_mock):
    httpx_mock.add_response(json=_payload([_make_item(1)]))

    connector = _make_connector()
    await connector.search("ai", max_results=1)

    request = httpx_mock.get_requests()[0]
    assert "User-Agent" in request.headers
    assert "mailto:" in request.headers["User-Agent"]
    assert "mailto" in request.url.params


@pytest.mark.asyncio
async def test_network_error_raises_connector_error_after_retries(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("boom"))
    httpx_mock.add_exception(httpx.ConnectError("boom"))
    httpx_mock.add_exception(httpx.ConnectError("boom"))

    connector = _make_connector()
    with pytest.raises(ConnectorError) as exc_info:
        await connector.search("ai", max_results=5)

    assert exc_info.value.source == "crossref"
    assert len(httpx_mock.get_requests()) == 3


@pytest.mark.asyncio
async def test_non_retryable_status_raises_connector_error_immediately(httpx_mock):
    # 404 is not retryable (only 5xx/429/network errors are) - surfaces immediately.
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
async def test_missing_authors_and_year_handled_gracefully(httpx_mock):
    sparse_item = {
        "title": ["Sparse Record"],
        "DOI": "10.1234/sparse.1",
        "URL": "https://doi.org/10.1234/sparse.1",
    }
    httpx_mock.add_response(json=_payload([sparse_item]))

    connector = _make_connector()
    results = await connector.search("ai", max_results=1)

    assert results[0].authors == []
    assert results[0].year is None
    assert results[0].title == "Sparse Record"


@pytest.mark.asyncio
async def test_search_uses_the_shared_rate_limiter(httpx_mock):
    httpx_mock.add_response(json=_payload([_make_item(1)]))

    calls: list[int] = []

    class _SpyRateLimiter:
        async def acquire(self) -> None:
            calls.append(1)

    connector = CrossrefConnector(rate_limiter=_SpyRateLimiter())
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
