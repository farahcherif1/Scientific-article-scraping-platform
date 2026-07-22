import httpx
import pytest

from app.connectors.pubmed import PubMedConnector
from app.domain.entities import ConnectorError
from app.infra.cache import clear_cache


class _NoopRateLimiter:
    async def acquire(self) -> None:
        return None


def _make_connector(**overrides) -> PubMedConnector:
    overrides.setdefault("rate_limiter", _NoopRateLimiter())
    overrides.setdefault("polite_pool_email", "team@example.com")
    return PubMedConnector(**overrides)


def _esearch_payload(pmids: list[str]) -> dict:
    return {"esearchresult": {"count": str(len(pmids)), "idlist": pmids}}


def _article_xml(
    pmid: str,
    *,
    title: str = "A PubMed Study",
    year: str | None = "2021",
    medline_date: str | None = None,
    doi: str | None = "10.1000/pubmed.example",
    abstract: str | None = "Background text. Results text.",
    authors_xml: str = "<Author><ForeName>Ada</ForeName><LastName>Lovelace</LastName></Author>",
    venue: str = "Journal of Examples",
) -> str:
    pub_date = f"<Year>{year}</Year>" if year else f"<MedlineDate>{medline_date}</MedlineDate>"
    abstract_xml = f"<Abstract><AbstractText>{abstract}</AbstractText></Abstract>" if abstract else ""
    doi_xml = f'<ArticleId IdType="doi">{doi}</ArticleId>' if doi else ""
    return f"""
    <PubmedArticle>
      <MedlineCitation>
        <PMID Version="1">{pmid}</PMID>
        <Article>
          <Journal>
            <Title>{venue}</Title>
            <JournalIssue><PubDate>{pub_date}</PubDate></JournalIssue>
          </Journal>
          <ArticleTitle>{title}</ArticleTitle>
          {abstract_xml}
          <AuthorList>{authors_xml}</AuthorList>
        </Article>
      </MedlineCitation>
      <PubmedData>
        <ArticleIdList>
          <ArticleId IdType="pubmed">{pmid}</ArticleId>
          {doi_xml}
        </ArticleIdList>
      </PubmedData>
    </PubmedArticle>
    """


def _articleset(articles_xml: list[str]) -> str:
    body = "\n".join(articles_xml)
    return f'<?xml version="1.0"?>\n<PubmedArticleSet>\n{body}\n</PubmedArticleSet>'


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.mark.asyncio
async def test_search_maps_core_fields(httpx_mock):
    httpx_mock.add_response(json=_esearch_payload(["1"]))
    httpx_mock.add_response(text=_articleset([_article_xml("1")]))

    connector = _make_connector()
    results = await connector.search("cancer", max_results=1)

    assert len(results) == 1
    article = results[0]
    assert article.title == "A PubMed Study"
    assert article.authors == ["Ada Lovelace"]
    assert article.year == 2021
    assert article.abstract == "Background text. Results text."
    assert article.doi == "10.1000/pubmed.example"
    assert article.venue == "Journal of Examples"
    assert article.url == "https://pubmed.ncbi.nlm.nih.gov/1/"
    assert article.source == "pubmed"
    assert article.search_keyword == "cancer"


@pytest.mark.asyncio
async def test_no_hits_returns_empty_list_without_efetch_call(httpx_mock):
    httpx_mock.add_response(json=_esearch_payload([]))

    connector = _make_connector()
    results = await connector.search("zzz_no_such_keyword", max_results=5)

    assert results == []
    assert len(httpx_mock.get_requests()) == 1  # efetch never called


@pytest.mark.asyncio
async def test_collective_name_author_is_used_when_present(httpx_mock):
    httpx_mock.add_response(json=_esearch_payload(["1"]))
    httpx_mock.add_response(
        text=_articleset([
            _article_xml("1", authors_xml="<Author><CollectiveName>Some Study Group</CollectiveName></Author>")
        ])
    )

    connector = _make_connector()
    results = await connector.search("ai", max_results=1)

    assert results[0].authors == ["Some Study Group"]


@pytest.mark.asyncio
async def test_medline_date_used_as_year_fallback(httpx_mock):
    httpx_mock.add_response(json=_esearch_payload(["1"]))
    httpx_mock.add_response(
        text=_articleset([_article_xml("1", year=None, medline_date="2019 Jan-Feb")])
    )

    connector = _make_connector()
    results = await connector.search("ai", max_results=1)

    assert results[0].year == 2019


@pytest.mark.asyncio
async def test_missing_abstract_does_not_drop_record(httpx_mock):
    httpx_mock.add_response(json=_esearch_payload(["1"]))
    httpx_mock.add_response(text=_articleset([_article_xml("1", abstract=None)]))

    connector = _make_connector()
    results = await connector.search("ai", max_results=1)

    assert len(results) == 1
    assert results[0].abstract is None


@pytest.mark.asyncio
async def test_invalid_doi_normalizes_to_none(httpx_mock):
    httpx_mock.add_response(json=_esearch_payload(["1"]))
    httpx_mock.add_response(text=_articleset([_article_xml("1", doi="not-a-doi")]))

    connector = _make_connector()
    results = await connector.search("ai", max_results=1)

    assert results[0].doi is None


@pytest.mark.asyncio
async def test_tool_and_email_sent_on_every_request(httpx_mock):
    httpx_mock.add_response(json=_esearch_payload(["1"]))
    httpx_mock.add_response(text=_articleset([_article_xml("1")]))

    connector = _make_connector(polite_pool_email="me@example.com")
    await connector.search("ai", max_results=1)

    requests = httpx_mock.get_requests()
    assert len(requests) == 2
    for request in requests:
        assert request.url.params["tool"] == "Team08-E26-Yonnovia"
        assert request.url.params["email"] == "me@example.com"


@pytest.mark.asyncio
async def test_api_key_added_when_configured(httpx_mock):
    httpx_mock.add_response(json=_esearch_payload(["1"]))
    httpx_mock.add_response(text=_articleset([_article_xml("1")]))

    connector = _make_connector(api_key="secret-key")
    await connector.search("ai", max_results=1)

    requests = httpx_mock.get_requests()
    assert all(r.url.params["api_key"] == "secret-key" for r in requests)


@pytest.mark.asyncio
async def test_network_error_on_esearch_raises_connector_error_after_retries(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("boom"))
    httpx_mock.add_exception(httpx.ConnectError("boom"))
    httpx_mock.add_exception(httpx.ConnectError("boom"))

    connector = _make_connector()
    with pytest.raises(ConnectorError) as exc_info:
        await connector.search("ai", max_results=5)

    assert exc_info.value.source == "pubmed"
    assert len(httpx_mock.get_requests()) == 3


@pytest.mark.asyncio
async def test_non_retryable_status_on_esearch_raises_immediately(httpx_mock):
    httpx_mock.add_response(status_code=404, text="Not Found")

    connector = _make_connector()
    with pytest.raises(ConnectorError):
        await connector.search("ai", max_results=5)

    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
async def test_persistent_5xx_on_efetch_raises_connector_error_after_max_retries(httpx_mock):
    httpx_mock.add_response(json=_esearch_payload(["1"]))
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=503)

    connector = _make_connector()
    with pytest.raises(ConnectorError):
        await connector.search("ai", max_results=5)

    assert len(httpx_mock.get_requests()) == 4  # 1 esearch + 3 efetch attempts


@pytest.mark.asyncio
async def test_429_on_esearch_retries_then_succeeds(httpx_mock):
    httpx_mock.add_response(status_code=429)
    httpx_mock.add_response(json=_esearch_payload(["1"]))
    httpx_mock.add_response(text=_articleset([_article_xml("1")]))

    connector = _make_connector()
    results = await connector.search("ai", max_results=1)

    assert len(results) == 1
    assert len(httpx_mock.get_requests()) == 3


@pytest.mark.asyncio
async def test_malformed_esearch_json_raises_connector_error(httpx_mock):
    httpx_mock.add_response(text="not json{{{")

    connector = _make_connector()
    with pytest.raises(ConnectorError):
        await connector.search("ai", max_results=5)


@pytest.mark.asyncio
async def test_malformed_efetch_xml_raises_connector_error(httpx_mock):
    httpx_mock.add_response(json=_esearch_payload(["1"]))
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
async def test_max_results_below_one_rejected():
    connector = _make_connector()
    with pytest.raises(ConnectorError):
        await connector.search("ai", max_results=0)


@pytest.mark.asyncio
async def test_search_uses_the_shared_rate_limiter_for_both_calls(httpx_mock):
    httpx_mock.add_response(json=_esearch_payload(["1"]))
    httpx_mock.add_response(text=_articleset([_article_xml("1")]))

    calls: list[int] = []

    class _SpyRateLimiter:
        async def acquire(self) -> None:
            calls.append(1)

    connector = PubMedConnector(rate_limiter=_SpyRateLimiter(), polite_pool_email="me@example.com")
    await connector.search("ai", max_results=1)

    assert calls == [1, 1]  # once for esearch, once for efetch


@pytest.mark.asyncio
async def test_second_identical_search_is_served_from_cache(httpx_mock):
    httpx_mock.add_response(json=_esearch_payload(["1"]))
    httpx_mock.add_response(text=_articleset([_article_xml("1")]))

    connector = _make_connector()
    first = await connector.search("ai", max_results=1)
    second = await connector.search("ai", max_results=1)  # no more mocks registered

    assert len(httpx_mock.get_requests()) == 2
    assert [a.title for a in first] == [a.title for a in second]


@pytest.mark.asyncio
async def test_multiple_articles_are_all_mapped(httpx_mock):
    httpx_mock.add_response(json=_esearch_payload(["1", "2", "3"]))
    httpx_mock.add_response(
        text=_articleset([_article_xml(str(i), title=f"Study {i}") for i in (1, 2, 3)])
    )

    connector = _make_connector()
    results = await connector.search("ai", max_results=3)

    assert [a.title for a in results] == ["Study 1", "Study 2", "Study 3"]
