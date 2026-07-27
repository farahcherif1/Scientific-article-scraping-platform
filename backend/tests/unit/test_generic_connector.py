"""
GenericConnector tests, using 3 of the real API shapes researched for
EP-custom-connectors (docs/custom-connectors.md) as mocked fixtures - proving
the config-driven mapping works across distinct auth + pagination + response
nesting combinations without any source-specific code:

  - HAL        - no auth,          offset pagination, flat author-string array
  - CORE       - api_key_header,   offset pagination + total count, nested author objects
  - Europe PMC - no auth,          cursor pagination,  single author string (not an array)
"""
import pytest

from app.connectors.generic import GenericConnector
from app.connectors.generic_config import (
    AuthConfig,
    AuthType,
    CustomConnectorConfig,
    FieldMapping,
    FieldMappingConfig,
    PaginationConfig,
    PaginationStyle,
    QueryMapping,
)
from app.domain.entities import ConnectorError


class _NoopRateLimiter:
    async def acquire(self) -> None:
        return None


def _make_connector(config: CustomConnectorConfig, slug: str = "custom_test") -> GenericConnector:
    return GenericConnector(slug=slug, config=config, rate_limiter=_NoopRateLimiter())


# ---------------------------------------------------------------------------
# HAL: base_url search/, start/rows offset pagination, no auth.
# authFullName_s is a flat array of strings (no [] needed in the path).
# ---------------------------------------------------------------------------

HAL_CONFIG = CustomConnectorConfig(
    base_url="https://api.archives-ouvertes.fr/search/",
    query_mapping=QueryMapping(keyword_param="q", static_params={"wt": "json"}),
    pagination=PaginationConfig(
        style=PaginationStyle.OFFSET,
        page_size=2,
        page_size_param="rows",
        offset_param="start",
        start_offset=0,
        results_path="response.docs",
        stop_when_empty=True,
    ),
    field_mapping=FieldMappingConfig(
        title=FieldMapping(path="title_s"),
        authors=FieldMapping(path="authFullName_s"),
        year=FieldMapping(path="producedDateY_i"),
        doi=FieldMapping(path="doiId_s"),
        abstract=FieldMapping(path="abstract_s"),
    ),
)


def _hal_doc(**overrides) -> dict:
    doc = {
        "title_s": "Deep Learning for NLP",
        "authFullName_s": ["Ada Lovelace", "Alan Turing"],
        "producedDateY_i": 2021,
        "doiId_s": "10.1234/hal.001",
        "abstract_s": "An abstract.",
    }
    doc.update(overrides)
    return doc


async def test_hal_style_maps_flat_author_array_and_sends_no_auth(httpx_mock):
    httpx_mock.add_response(json={"response": {"docs": [_hal_doc()]}})

    connector = _make_connector(HAL_CONFIG)
    articles = await connector.search("nlp", max_results=5)

    assert len(articles) == 1
    article = articles[0]
    assert article.title == "Deep Learning for NLP"
    assert article.authors == ["Ada Lovelace", "Alan Turing"]
    assert article.year == 2021
    assert article.doi == "10.1234/hal.001"
    assert article.source == "custom_test"

    request = httpx_mock.get_requests()[0]
    assert "Authorization" not in request.headers
    assert dict(request.url.params)["start"] == "0"
    assert dict(request.url.params)["rows"] == "2"


async def test_hal_style_stops_when_a_page_is_shorter_than_page_size(httpx_mock):
    # page_size=2 but only 1 doc comes back -> stop_when_empty treats this as the last page.
    httpx_mock.add_response(json={"response": {"docs": [_hal_doc()]}})

    connector = _make_connector(HAL_CONFIG)
    articles = await connector.search("nlp", max_results=10)

    assert len(articles) == 1
    assert len(httpx_mock.get_requests()) == 1


async def test_hal_style_paginates_across_offset_until_max_results(httpx_mock):
    httpx_mock.add_response(json={"response": {"docs": [_hal_doc(), _hal_doc(title_s="Second")]}})
    httpx_mock.add_response(json={"response": {"docs": [_hal_doc(title_s="Third")]}})

    connector = _make_connector(HAL_CONFIG)
    articles = await connector.search("nlp", max_results=3)

    assert [a.title for a in articles] == ["Deep Learning for NLP", "Second", "Third"]
    requests = httpx_mock.get_requests()
    assert dict(requests[0].url.params)["start"] == "0"
    assert dict(requests[1].url.params)["start"] == "2"


# ---------------------------------------------------------------------------
# CORE: api_key_header auth, offset + total-count pagination, nested authors.
# ---------------------------------------------------------------------------

CORE_CONFIG = CustomConnectorConfig(
    base_url="https://api.core.ac.uk/v3/search/works",
    auth=AuthConfig(type=AuthType.API_KEY_HEADER, key_name="Authorization", key_value="Bearer secret-key"),
    query_mapping=QueryMapping(keyword_param="q"),
    pagination=PaginationConfig(
        style=PaginationStyle.OFFSET,
        page_size=2,
        page_size_param="limit",
        offset_param="offset",
        results_path="results",
        total_path="totalHits",
    ),
    field_mapping=FieldMappingConfig(
        title=FieldMapping(path="title"),
        authors=FieldMapping(path="authors[].name"),
        year=FieldMapping(path="yearPublished"),
        doi=FieldMapping(path="doi"),
        abstract=FieldMapping(path="abstract"),
        citation_count=FieldMapping(path="citationCount"),
    ),
)


def _core_record(**overrides) -> dict:
    record = {
        "title": "Federated Learning Survey",
        "authors": [{"name": "Jane Doe"}, {"name": "John Smith"}],
        "yearPublished": 2022,
        "doi": "https://doi.org/10.5555/core.002",
        "abstract": "A survey.",
        "citationCount": 17,
    }
    record.update(overrides)
    return record


async def test_core_style_sends_bearer_header_and_maps_nested_authors(httpx_mock):
    httpx_mock.add_response(json={"totalHits": 1, "results": [_core_record()]})

    connector = _make_connector(CORE_CONFIG)
    articles = await connector.search("federated learning", max_results=5)

    assert len(articles) == 1
    article = articles[0]
    assert article.authors == ["Jane Doe", "John Smith"]
    assert article.doi == "10.5555/core.002"  # normalized: https://doi.org/ stripped, lowercased
    assert article.citation_count == 17

    request = httpx_mock.get_requests()[0]
    assert request.headers["Authorization"] == "Bearer secret-key"


async def test_core_style_stops_at_reported_total_hits(httpx_mock):
    # A *full* page (len(results) == page_size) so stop_when_empty's
    # short-page heuristic can't be what stops the loop - only total_path
    # (totalHits == collected) should.
    httpx_mock.add_response(
        json={"totalHits": 2, "results": [_core_record(), _core_record(title="Second")]}
    )

    connector = _make_connector(CORE_CONFIG)
    articles = await connector.search("federated learning", max_results=10)

    assert len(articles) == 2
    assert len(httpx_mock.get_requests()) == 1  # totalHits=2 stopped the loop after 1 page


# ---------------------------------------------------------------------------
# Europe PMC: no auth, cursor pagination, single author string (not a list).
# ---------------------------------------------------------------------------

EUROPEPMC_CONFIG = CustomConnectorConfig(
    base_url="https://www.ebi.ac.uk/europepmc/webservices/rest/search",
    query_mapping=QueryMapping(keyword_param="query", static_params={"format": "json"}),
    pagination=PaginationConfig(
        style=PaginationStyle.CURSOR,
        page_size=2,
        page_size_param="pageSize",
        cursor_param="cursorMark",
        next_cursor_path="nextCursorMark",
        results_path="resultList.result",
    ),
    field_mapping=FieldMappingConfig(
        title=FieldMapping(path="title"),
        authors=FieldMapping(path="authorString"),
        year=FieldMapping(path="pubYear"),
        doi=FieldMapping(path="doi"),
        abstract=FieldMapping(path="abstractText"),
    ),
)


def _epmc_result(**overrides) -> dict:
    result = {
        "title": "CRISPR Advances",
        "authorString": "Doe J, Smith J.",
        "pubYear": "2020",
        "doi": "10.1000/epmc.003",
        "abstractText": "Abstract text.",
    }
    result.update(overrides)
    return result


async def test_europepmc_style_wraps_scalar_author_string_into_a_single_element_list(httpx_mock):
    httpx_mock.add_response(
        json={"resultList": {"result": [_epmc_result()]}, "nextCursorMark": None}
    )

    connector = _make_connector(EUROPEPMC_CONFIG)
    articles = await connector.search("crispr", max_results=5)

    assert len(articles) == 1
    assert articles[0].authors == ["Doe J, Smith J."]
    assert articles[0].year == 2020

    request = httpx_mock.get_requests()[0]
    assert "cursorMark" not in dict(request.url.params)  # first request has no cursor yet


async def test_europepmc_style_follows_next_cursor_mark(httpx_mock):
    httpx_mock.add_response(
        json={
            "resultList": {"result": [_epmc_result(), _epmc_result(title="Second")]},
            "nextCursorMark": "AoIIP",
        }
    )
    httpx_mock.add_response(
        json={"resultList": {"result": [_epmc_result(title="Third")]}, "nextCursorMark": None}
    )

    connector = _make_connector(EUROPEPMC_CONFIG)
    articles = await connector.search("crispr", max_results=3)

    assert [a.title for a in articles] == ["CRISPR Advances", "Second", "Third"]
    requests = httpx_mock.get_requests()
    assert "cursorMark" not in dict(requests[0].url.params)
    assert dict(requests[1].url.params)["cursorMark"] == "AoIIP"


async def test_europepmc_style_stops_when_next_cursor_mark_is_absent(httpx_mock):
    httpx_mock.add_response(
        json={"resultList": {"result": [_epmc_result(), _epmc_result(title="Second")]}, "nextCursorMark": None}
    )

    connector = _make_connector(EUROPEPMC_CONFIG)
    articles = await connector.search("crispr", max_results=10)

    assert len(articles) == 2
    assert len(httpx_mock.get_requests()) == 1


# ---------------------------------------------------------------------------
# Shared behaviors (auth query param, health check, error propagation, aclose)
# ---------------------------------------------------------------------------


async def test_api_key_query_param_auth_is_sent(httpx_mock):
    config = CustomConnectorConfig(
        base_url="https://api.example.org/search",
        auth=AuthConfig(type=AuthType.API_KEY_QUERY_PARAM, key_name="apikey", key_value="my-key"),
        query_mapping=QueryMapping(keyword_param="querytext"),
        pagination=PaginationConfig(style=PaginationStyle.NONE, results_path="articles"),
        field_mapping=FieldMappingConfig(title=FieldMapping(path="title")),
    )
    httpx_mock.add_response(json={"articles": [{"title": "Example"}]})

    connector = _make_connector(config)
    await connector.search("x", max_results=5)

    request = httpx_mock.get_requests()[0]
    assert dict(request.url.params)["apikey"] == "my-key"


async def test_missing_title_defaults_to_empty_string_not_dropped(httpx_mock):
    httpx_mock.add_response(json={"response": {"docs": [{"authFullName_s": ["Solo Author"]}]}})

    connector = _make_connector(HAL_CONFIG)
    articles = await connector.search("nlp", max_results=1)

    assert len(articles) == 1
    assert articles[0].title == ""
    assert articles[0].authors == ["Solo Author"]


async def test_persistent_5xx_raises_connector_error(httpx_mock):
    for _ in range(3):  # MAX_RETRIES=2 -> 3 total attempts
        httpx_mock.add_response(status_code=503)

    connector = _make_connector(HAL_CONFIG)
    with pytest.raises(ConnectorError):
        await connector.search("nlp", max_results=5)


async def test_none_style_makes_exactly_one_request_regardless_of_max_results(httpx_mock):
    config = CustomConnectorConfig(
        base_url="https://api.example.org/search",
        query_mapping=QueryMapping(keyword_param="q"),
        pagination=PaginationConfig(style=PaginationStyle.NONE, results_path="items"),
        field_mapping=FieldMappingConfig(title=FieldMapping(path="title")),
    )
    httpx_mock.add_response(json={"items": [{"title": "A"}, {"title": "B"}]})

    connector = _make_connector(config)
    articles = await connector.search("x", max_results=100)

    assert len(articles) == 2
    assert len(httpx_mock.get_requests()) == 1


async def test_health_check_returns_true_on_200(httpx_mock):
    httpx_mock.add_response(json={"response": {"docs": []}})
    connector = _make_connector(HAL_CONFIG)
    assert await connector.health_check() is True


async def test_health_check_returns_false_on_error_status(httpx_mock):
    httpx_mock.add_response(status_code=500)
    connector = _make_connector(HAL_CONFIG)
    assert await connector.health_check() is False
