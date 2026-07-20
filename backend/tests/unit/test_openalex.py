import httpx
import pytest

from app.connectors.base import SearchFilters
from app.connectors.openalex import OpenAlexConnector
from app.domain.entities import ConnectorError, SourceEnum
from app.infra.cache import clear_cache


class _NoopRateLimiter:
    async def acquire(self) -> None:
        return None


def _make_connector() -> OpenAlexConnector:
    return OpenAlexConnector(
        polite_pool_email="team08@example.com",
        rate_limiter=_NoopRateLimiter(),
    )


def _make_record(**overrides) -> dict:
    record = {
        "id": "https://openalex.org/W123",
        "doi": "https://doi.org/10.1234/ABC",
        "title": "A Great Paper",
        "display_name": "A Great Paper",
        "publication_year": 2023,
        "cited_by_count": 42,
        "authorships": [
            {"author": {"display_name": "Jane Doe"}},
            {"author": {"display_name": "John Smith"}},
        ],
        "concepts": [{"display_name": "Machine Learning"}],
        "primary_location": {"source": {"display_name": "Journal of Things"}},
        "abstract_inverted_index": {"Hello": [0], "world": [1]},
    }
    record.update(overrides)
    return record


def _page(results: list[dict], next_cursor: str | None) -> dict:
    return {"results": results, "meta": {"next_cursor": next_cursor}}


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


async def test_every_request_sends_mailto(httpx_mock):
    httpx_mock.add_response(json=_page([_make_record()], next_cursor=None))

    connector = _make_connector()
    await connector.search("ai", max_results=5)

    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert requests[0].url.params["mailto"] == "team08@example.com"


async def test_field_mapping(httpx_mock):
    httpx_mock.add_response(json=_page([_make_record()], next_cursor=None))

    connector = _make_connector()
    [article] = await connector.search("ai", max_results=5)

    assert article.source == SourceEnum.OPENALEX
    assert article.title == "A Great Paper"
    assert article.authors == ["Jane Doe", "John Smith"]
    assert article.year == 2023
    assert article.citation_count == 42  # cited_by_count -> citation_count
    assert article.domain == "Machine Learning"  # concepts -> domain
    assert article.venue == "Journal of Things"
    assert article.doi == "10.1234/abc"  # https://doi.org/ stripped + lowercased
    assert article.abstract == "Hello world"  # inverted index reconstructed


async def test_primary_location_with_null_source_does_not_crash(httpx_mock):
    # Seen live: primary_location is present but its "source" key is null
    # (not absent) when OpenAlex hasn't identified a venue for the work.
    record = _make_record(primary_location={"source": None})
    httpx_mock.add_response(json=_page([record], next_cursor=None))

    connector = _make_connector()
    [article] = await connector.search("ai", max_results=5)

    assert article.venue is None


async def test_missing_optional_fields_are_none_not_dropped(httpx_mock):
    sparse = _make_record(
        doi=None,
        authorships=[],
        concepts=[],
        primary_location=None,
        abstract_inverted_index=None,
    )
    httpx_mock.add_response(json=_page([sparse], next_cursor=None))

    connector = _make_connector()
    [article] = await connector.search("ai", max_results=5)

    assert article.doi is None
    assert article.authors == []
    assert article.domain is None
    assert article.venue is None
    assert article.abstract is None


async def test_pagination_stops_cleanly_at_max_results(httpx_mock):
    page1 = [_make_record(id=f"W{i}") for i in range(2)]
    page2 = [_make_record(id="W2")]
    httpx_mock.add_response(json=_page(page1, next_cursor="cursor-2"))
    httpx_mock.add_response(json=_page(page2, next_cursor="cursor-3"))

    connector = _make_connector()
    articles = await connector.search("ai", max_results=3)

    assert len(articles) == 3
    requests = httpx_mock.get_requests()
    assert len(requests) == 2  # stopped once max_results was reached, no 3rd page fetched
    assert requests[0].url.params["per_page"] == "3"
    assert requests[1].url.params["per_page"] == "1"


async def test_pagination_truncates_overfetched_page(httpx_mock):
    # Defensive case: a page returns more records than still needed.
    page1 = [_make_record(id=f"W{i}") for i in range(5)]
    httpx_mock.add_response(json=_page(page1, next_cursor="cursor-2"))

    connector = _make_connector()
    articles = await connector.search("ai", max_results=3)

    assert len(articles) == 3
    assert len(httpx_mock.get_requests()) == 1  # never asked for a page it didn't need


async def test_pagination_stops_when_no_more_results(httpx_mock):
    httpx_mock.add_response(json=_page([_make_record()], next_cursor=None))

    connector = _make_connector()
    articles = await connector.search("ai", max_results=10)

    assert len(articles) == 1
    assert len(httpx_mock.get_requests()) == 1


async def test_year_filters_applied(httpx_mock):
    httpx_mock.add_response(json=_page([], next_cursor=None))

    connector = _make_connector()
    await connector.search("ai", max_results=5, filters=SearchFilters(year_from=2020, year_to=2022))

    request = httpx_mock.get_requests()[0]
    assert request.url.params["filter"] == "from_publication_date:2020-01-01,to_publication_date:2022-12-31"


async def test_429_retries_then_succeeds(httpx_mock):
    httpx_mock.add_response(status_code=429)
    httpx_mock.add_response(json=_page([_make_record()], next_cursor=None))

    connector = _make_connector()
    articles = await connector.search("ai", max_results=5)

    assert len(articles) == 1
    assert len(httpx_mock.get_requests()) == 2


async def test_persistent_5xx_raises_connector_error_after_max_retries(httpx_mock):
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=503)

    connector = _make_connector()
    with pytest.raises(ConnectorError) as exc_info:
        await connector.search("ai", max_results=5)

    assert len(httpx_mock.get_requests()) == 3  # 1 initial attempt + 2 retries, then give up
    assert exc_info.value.source == "openalex"
    assert exc_info.value.keyword == "ai"


async def test_second_identical_search_is_served_from_cache(httpx_mock):
    httpx_mock.add_response(json=_page([_make_record()], next_cursor=None))

    connector = _make_connector()
    first = await connector.search("ai", max_results=5)
    second = await connector.search("ai", max_results=5)  # no mock registered for a 2nd HTTP call

    assert len(httpx_mock.get_requests()) == 1
    assert [a.title for a in first] == [a.title for a in second]
    assert second[0].citation_count == 42  # cache hit still goes through field mapping


async def test_health_check_true_on_200(httpx_mock):
    httpx_mock.add_response(status_code=200, json=_page([], next_cursor=None))

    connector = _make_connector()
    assert await connector.health_check() is True


async def test_health_check_false_on_network_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("boom"))

    connector = _make_connector()
    assert await connector.health_check() is False


def test_reconstruct_abstract_orders_words_by_position():
    inverted = {"world": [1, 3], "Hello": [0], "again": [2]}
    result = OpenAlexConnector._reconstruct_abstract(inverted)
    assert result == "Hello world again world"


def test_reconstruct_abstract_handles_empty_index():
    assert OpenAlexConnector._reconstruct_abstract(None) is None
    assert OpenAlexConnector._reconstruct_abstract({}) is None
