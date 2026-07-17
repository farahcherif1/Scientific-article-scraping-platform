import httpx
import pytest

from app.connectors.arxiv import ARXIV_API_URL, ArxivConnector
from app.domain.entities import ConnectorError
from app.infra.cache import clear_cache


class _NoopRateLimiter:
    async def acquire(self) -> None:
        return None


def _make_connector(**overrides) -> ArxivConnector:
    overrides.setdefault("rate_limiter", _NoopRateLimiter())
    return ArxivConnector(**overrides)


def _make_feed(n: int) -> str:
    entries = "\n".join(
        f"""
        <entry>
          <id>http://arxiv.org/abs/2301.0000{i}v1</id>
          <title>Large Language Models Study {i}</title>
          <summary>Abstract number {i} about large language models and reasoning.</summary>
          <published>2023-06-{(i % 28) + 1:02d}T00:00:00Z</published>
          <author><name>Author {i} A</name></author>
          <author><name>Author {i} B</name></author>
          <category term="cs.CL"/>
          <arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom" term="cs.CL"/>
        </entry>
        """
        for i in range(n)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
{entries}
</feed>"""


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.mark.asyncio
async def test_search_returns_records_with_required_fields(httpx_mock):
    httpx_mock.add_response(url=httpx.URL(ARXIV_API_URL).copy_merge_params(
        {"search_query": "all:large language models", "start": 0, "max_results": 10}
    ), text=_make_feed(10))

    connector = _make_connector()
    results = await connector.search("large language models", max_results=10)

    assert len(results) >= 10
    for article in results:
        assert article.title
        assert article.authors
        assert article.year
        assert article.abstract
        assert article.url
        assert article.source == "arxiv"
        assert article.search_keyword == "large language models"


@pytest.mark.asyncio
async def test_search_maps_categories_and_domain(httpx_mock):
    httpx_mock.add_response(text=_make_feed(1))

    connector = _make_connector()
    results = await connector.search("ai", max_results=1)

    assert results[0].domain == "cs.CL"
    assert "cs.CL" in results[0].categories


@pytest.mark.asyncio
async def test_network_error_raises_connector_error_after_retries(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("boom"))
    httpx_mock.add_exception(httpx.ConnectError("boom"))
    httpx_mock.add_exception(httpx.ConnectError("boom"))

    connector = _make_connector()
    with pytest.raises(ConnectorError) as exc_info:
        await connector.search("ai", max_results=5)

    assert exc_info.value.source == "arxiv"
    assert len(httpx_mock.get_requests()) == 3  # 1 initial attempt + 2 retries, then give up


@pytest.mark.asyncio
async def test_non_200_response_raises_connector_error(httpx_mock):
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

    assert len(httpx_mock.get_requests()) == 3  # 1 initial attempt + 2 retries, then give up


@pytest.mark.asyncio
async def test_429_retries_then_succeeds(httpx_mock):
    httpx_mock.add_response(status_code=429)
    httpx_mock.add_response(text=_make_feed(1))

    connector = _make_connector()
    results = await connector.search("ai", max_results=1)

    assert len(results) == 1
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.asyncio
async def test_malformed_xml_raises_connector_error(httpx_mock):
    httpx_mock.add_response(text="<not-valid-xml")

    connector = _make_connector()
    with pytest.raises(ConnectorError):
        await connector.search("ai", max_results=5)


@pytest.mark.asyncio
async def test_empty_keyword_rejected():
    connector = _make_connector()
    with pytest.raises(ConnectorError):
        await connector.search("   ", max_results=5)


@pytest.mark.asyncio
async def test_search_uses_the_shared_rate_limiter(httpx_mock):
    httpx_mock.add_response(text=_make_feed(1))

    calls: list[int] = []

    class _SpyRateLimiter:
        async def acquire(self) -> None:
            calls.append(1)

    connector = ArxivConnector(rate_limiter=_SpyRateLimiter())
    await connector.search("ai", max_results=1)

    assert calls == [1]


@pytest.mark.asyncio
async def test_second_identical_search_is_served_from_cache(httpx_mock):
    httpx_mock.add_response(text=_make_feed(1))

    connector = _make_connector()
    first = await connector.search("ai", max_results=1)
    second = await connector.search("ai", max_results=1)  # no 2nd mock registered

    assert len(httpx_mock.get_requests()) == 1
    assert [a.title for a in first] == [a.title for a in second]
