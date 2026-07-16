import httpx
import pytest

from app.connectors.arxiv import ARXIV_API_URL, ArxivConnector
from app.domain.exceptions import ConnectorError


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


@pytest.mark.asyncio
async def test_search_returns_records_with_required_fields(httpx_mock):
    httpx_mock.add_response(url=httpx.URL(ARXIV_API_URL).copy_merge_params(
        {"search_query": "all:large language models", "start": 0, "max_results": 10}
    ), text=_make_feed(10))

    connector = ArxivConnector()
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

    connector = ArxivConnector()
    results = await connector.search("ai", max_results=1)

    assert results[0].domain == "cs.CL"
    assert "cs.CL" in results[0].categories


@pytest.mark.asyncio
async def test_network_error_raises_connector_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("boom"))

    connector = ArxivConnector()
    with pytest.raises(ConnectorError) as exc_info:
        await connector.search("ai", max_results=5)

    assert exc_info.value.source == "arxiv"


@pytest.mark.asyncio
async def test_non_200_response_raises_connector_error(httpx_mock):
    httpx_mock.add_response(status_code=503, text="Service Unavailable")

    connector = ArxivConnector()
    with pytest.raises(ConnectorError):
        await connector.search("ai", max_results=5)


@pytest.mark.asyncio
async def test_malformed_xml_raises_connector_error(httpx_mock):
    httpx_mock.add_response(text="<not-valid-xml")

    connector = ArxivConnector()
    with pytest.raises(ConnectorError):
        await connector.search("ai", max_results=5)


@pytest.mark.asyncio
async def test_empty_keyword_rejected():
    connector = ArxivConnector()
    with pytest.raises(ConnectorError):
        await connector.search("   ", max_results=5)


@pytest.mark.asyncio
async def test_rate_limit_enforced_between_calls(httpx_mock, monkeypatch):
    httpx_mock.add_response(text=_make_feed(1))
    httpx_mock.add_response(text=_make_feed(1))

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr("app.connectors.arxiv.asyncio.sleep", fake_sleep)

    connector = ArxivConnector()
    await connector.search("ai", max_results=1)
    await connector.search("ai", max_results=1)

    assert len(sleep_calls) == 1
    assert sleep_calls[0] > 2.9
