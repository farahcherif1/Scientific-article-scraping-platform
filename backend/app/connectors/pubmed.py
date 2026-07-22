"""
PubMed connector (E-utilities) — reintroduces the source that was previously
dropped as dead scaffolding (see docs/limitations.md), now with a real
implementation. Follows the same shared-infra structure as the other
connectors: the resilient HTTP layer (US-03.6, retries on 5xx/429/network
errors with exponential backoff), the shared per-source rate limiter, and the
in-memory response cache.

Docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/
Two-step lookup, since E-utilities has no single search+fetch endpoint:
  1. esearch — keyword -> list of PMIDs (JSON)
  2. efetch  — PMIDs -> full records (XML)
Both requests carry `tool` + `email` per NCBI's usage policy (Appendix B,
rule 7's polite-identification requirement, same spirit as OpenAlex/Crossref's
mailto). An optional `api_key` (settings.pubmed_api_key) raises the allowed
rate from 3 req/s to 10 req/s but is not required.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from xml.etree import ElementTree

import httpx

from app.config import settings
from app.connectors.base import BaseConnector
from app.connectors.crossref import normalize_doi
from app.domain.entities import ConnectorError, RawArticle, SourceEnum
from app.infra.cache import get_cached, set_cached
from app.infra.retries import call_with_retry
from app.orchestrator.rate_limiter import PUBMED_RATE_LIMITER

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

TOOL_NAME = "Team08-E26-Yonnovia"


class PubMedConnector(BaseConnector):
    name = "pubmed"

    def __init__(
        self,
        *,
        polite_pool_email: Optional[str] = None,
        api_key: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        rate_limiter=PUBMED_RATE_LIMITER,
        connect_timeout_s: float = 10.0,
        read_timeout_s: float = 30.0,
    ):
        self._email = polite_pool_email or settings.polite_pool_email
        self._api_key = api_key if api_key is not None else settings.pubmed_api_key
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=connect_timeout_s, read=read_timeout_s,
                write=read_timeout_s, pool=read_timeout_s,
            ),
            follow_redirects=True,
        )
        self._rate_limiter = rate_limiter

    def _identity_params(self) -> dict:
        params = {"tool": TOOL_NAME, "email": self._email}
        if self._api_key:
            params["api_key"] = self._api_key
        return params

    async def search(
        self,
        keyword: str,
        max_results: int = 10,
        filters: dict | None = None,
    ) -> list[RawArticle]:
        if not keyword or not keyword.strip():
            raise ConnectorError(
                source=SourceEnum.PUBMED,
                endpoint=ESEARCH_URL,
                keyword=keyword,
                error_class="InvalidInput",
                message="Keyword must not be empty.",
            )
        if max_results < 1:
            raise ConnectorError(
                source=SourceEnum.PUBMED,
                endpoint=ESEARCH_URL,
                keyword=keyword,
                error_class="InvalidInput",
                message="max_results must be at least 1.",
            )

        cache_params = {"max_results": max_results}
        cached = get_cached(self.name, keyword, cache_params)
        if cached is not None:
            return [self._map_to_raw_article(record, keyword) for record in cached]

        pmids = await self._esearch(keyword, max_results)
        if not pmids:
            set_cached(self.name, keyword, cache_params, [])
            return []

        raw_records = await self._efetch(pmids, keyword)

        set_cached(self.name, keyword, cache_params, raw_records)
        return [self._map_to_raw_article(record, keyword) for record in raw_records]

    # ------------------------------------------------------------------
    # E-utilities calls
    # ------------------------------------------------------------------

    async def _esearch(self, keyword: str, max_results: int) -> list[str]:
        params = {
            "db": "pubmed",
            "term": keyword,
            "retmax": max_results,
            "retmode": "json",
            **self._identity_params(),
        }

        await self._rate_limiter.acquire()

        async def _do_request(p=params):
            return await self._client.get(ESEARCH_URL, params=p)

        response = await call_with_retry(
            _do_request, source=self.name, endpoint=ESEARCH_URL, keyword=keyword,
        )

        if response.status_code != 200:
            raise ConnectorError(
                source=SourceEnum.PUBMED,
                endpoint=ESEARCH_URL,
                keyword=keyword,
                error_class=f"HTTP{response.status_code}",
                message=f"PubMed esearch returned HTTP {response.status_code} for keyword '{keyword}'.",
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorError(
                source=SourceEnum.PUBMED,
                endpoint=ESEARCH_URL,
                keyword=keyword,
                error_class="ParseError",
                message=f"Could not parse PubMed esearch response: {exc}",
            ) from exc

        return payload.get("esearchresult", {}).get("idlist", [])

    async def _efetch(self, pmids: list[str], keyword: str) -> list[dict]:
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            **self._identity_params(),
        }

        await self._rate_limiter.acquire()

        async def _do_request(p=params):
            return await self._client.get(EFETCH_URL, params=p)

        response = await call_with_retry(
            _do_request, source=self.name, endpoint=EFETCH_URL, keyword=keyword,
        )

        if response.status_code != 200:
            raise ConnectorError(
                source=SourceEnum.PUBMED,
                endpoint=EFETCH_URL,
                keyword=keyword,
                error_class=f"HTTP{response.status_code}",
                message=f"PubMed efetch returned HTTP {response.status_code} for keyword '{keyword}'.",
            )

        try:
            return self._parse_articleset(response.text)
        except ElementTree.ParseError as exc:
            raise ConnectorError(
                source=SourceEnum.PUBMED,
                endpoint=EFETCH_URL,
                keyword=keyword,
                error_class="ParseError",
                message=f"Could not parse PubMed efetch response: {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # XML parsing / mapping
    # ------------------------------------------------------------------

    def _parse_articleset(self, xml_text: str) -> list[dict]:
        root = ElementTree.fromstring(xml_text)
        records: list[dict] = []

        for pubmed_article in root.findall("PubmedArticle"):
            article_el = pubmed_article.find("MedlineCitation/Article")
            if article_el is None:
                continue

            title_el = article_el.find("ArticleTitle")
            title = _clean_text("".join(title_el.itertext())) if title_el is not None else ""
            if not title:
                continue  # malformed record - skip rather than emit a broken one

            authors = []
            for author_el in article_el.findall("AuthorList/Author"):
                collective = author_el.find("CollectiveName")
                if collective is not None and collective.text:
                    authors.append(_clean_text(collective.text))
                    continue
                fore = author_el.find("ForeName")
                last = author_el.find("LastName")
                full_name = " ".join(
                    part.text.strip() for part in (fore, last) if part is not None and part.text
                )
                if full_name:
                    authors.append(full_name)

            year = None
            pub_date = article_el.find("Journal/JournalIssue/PubDate")
            if pub_date is not None:
                year_el = pub_date.find("Year")
                if year_el is not None and year_el.text:
                    try:
                        year = int(year_el.text.strip())
                    except ValueError:
                        year = None
                else:
                    medline_date = pub_date.find("MedlineDate")
                    if medline_date is not None and medline_date.text:
                        digits = "".join(c for c in medline_date.text[:4] if c.isdigit())
                        year = int(digits) if len(digits) == 4 else None

            abstract_parts = [
                _clean_text("".join(el.itertext()))
                for el in article_el.findall("Abstract/AbstractText")
            ]
            abstract = " ".join(part for part in abstract_parts if part) or None

            venue_el = article_el.find("Journal/Title")
            venue = _clean_text(venue_el.text) if venue_el is not None and venue_el.text else None

            pmid_el = pubmed_article.find("MedlineCitation/PMID")
            pmid = pmid_el.text.strip() if pmid_el is not None and pmid_el.text else None
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None

            doi = None
            for article_id in pubmed_article.findall("PubmedData/ArticleIdList/ArticleId"):
                if article_id.get("IdType") == "doi" and article_id.text:
                    doi = article_id.text.strip()
                    break
            if doi is None:
                for eloc in article_el.findall("ELocationID"):
                    if eloc.get("EIdType") == "doi" and eloc.text:
                        doi = eloc.text.strip()
                        break
            doi = normalize_doi(doi)

            records.append({
                "title": title,
                "authors": authors,
                "year": year,
                "abstract": abstract,
                "url": url,
                "doi": doi,
                "venue": venue,
            })

        return records

    def _map_to_raw_article(self, record: dict, keyword: str) -> RawArticle:
        return RawArticle(
            source=SourceEnum.PUBMED,
            search_keyword=keyword,
            collection_date=datetime.now(timezone.utc),
            title=record["title"],
            authors=record["authors"],
            year=record["year"],
            abstract=record["abstract"],
            url=record["url"],
            doi=record["doi"],
            venue=record["venue"],
        )

    async def health_check(self) -> bool:
        try:
            response = await self._client.get(
                ESEARCH_URL,
                params={"db": "pubmed", "term": "test", "retmax": 1, "retmode": "json", **self._identity_params()},
            )
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()


def _clean_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.split())
