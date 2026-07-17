"""
arXiv connector (US-03.1) — follows the same shared-infra structure as
OpenAlexConnector (US-03.2): the resilient HTTP layer (US-03.6, retries on
5xx/429/network errors with exponential backoff), the shared per-source rate
limiter, and the in-memory response cache.

Docs: https://arxiv.org/help/api/user-manual
Rate limit per arXiv's own guidance: ~1 request every 3 seconds
(settings.rate_limit_arxiv_interval_s / ARXIV_RATE_LIMITER).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from xml.etree import ElementTree

import httpx

from app.connectors.base import BaseConnector
from app.domain.entities import ConnectorError, RawArticle, SourceEnum
from app.infra.cache import get_cached, set_cached
from app.infra.retries import call_with_retry
from app.orchestrator.rate_limiter import ARXIV_RATE_LIMITER

ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"

ARXIV_API_URL = "https://export.arxiv.org/api/query"


class ArxivConnector(BaseConnector):
    name = "arxiv"

    def __init__(
        self,
        *,
        http_client: Optional[httpx.AsyncClient] = None,
        rate_limiter=ARXIV_RATE_LIMITER,
        connect_timeout_s: float = 10.0,
        read_timeout_s: float = 30.0,
    ):
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=connect_timeout_s, read=read_timeout_s,
                write=read_timeout_s, pool=read_timeout_s,
            ),
            follow_redirects=True,
        )
        self._rate_limiter = rate_limiter

    async def search(
        self,
        keyword: str,
        max_results: int = 10,
        filters: dict | None = None,
    ) -> list[RawArticle]:
        if not keyword or not keyword.strip():
            raise ConnectorError(
                source=SourceEnum.ARXIV,
                endpoint=ARXIV_API_URL,
                keyword=keyword,
                error_class="InvalidInput",
                message="Keyword must not be empty.",
            )
        if max_results < 1:
            raise ConnectorError(
                source=SourceEnum.ARXIV,
                endpoint=ARXIV_API_URL,
                keyword=keyword,
                error_class="InvalidInput",
                message="max_results must be at least 1.",
            )

        cache_params = {"max_results": max_results}
        cached = get_cached(self.name, keyword, cache_params)
        if cached is not None:
            return [self._map_to_raw_article(record, keyword) for record in cached]

        params = {
            "search_query": f"all:{keyword}",
            "start": 0,
            "max_results": max_results,
        }

        await self._rate_limiter.acquire()

        async def _do_request(p=params):
            return await self._client.get(ARXIV_API_URL, params=p)

        response = await call_with_retry(
            _do_request,
            source=self.name,
            endpoint=ARXIV_API_URL,
            keyword=keyword,
        )

        if response.status_code != 200:
            raise ConnectorError(
                source=SourceEnum.ARXIV,
                endpoint=ARXIV_API_URL,
                keyword=keyword,
                error_class=f"HTTP{response.status_code}",
                message=f"arXiv returned HTTP {response.status_code} for keyword '{keyword}'.",
            )

        try:
            raw_records = self._parse_feed(response.text)
        except ElementTree.ParseError as exc:
            raise ConnectorError(
                source=SourceEnum.ARXIV,
                endpoint=ARXIV_API_URL,
                keyword=keyword,
                error_class="ParseError",
                message=f"Could not parse arXiv response: {exc}",
            ) from exc

        set_cached(self.name, keyword, cache_params, raw_records)
        return [self._map_to_raw_article(record, keyword) for record in raw_records]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_feed(self, xml_text: str) -> list[dict]:
        root = ElementTree.fromstring(xml_text)
        records: list[dict] = []

        for entry in root.findall(f"{ATOM_NS}entry"):
            title_el = entry.find(f"{ATOM_NS}title")
            title = _clean_text(title_el.text) if title_el is not None else ""
            if not title:
                # Malformed entry from the API - skip rather than emit a broken record.
                continue

            summary_el = entry.find(f"{ATOM_NS}summary")
            published_el = entry.find(f"{ATOM_NS}published")
            id_el = entry.find(f"{ATOM_NS}id")

            authors = [
                _clean_text(name_el.text)
                for author_el in entry.findall(f"{ATOM_NS}author")
                for name_el in [author_el.find(f"{ATOM_NS}name")]
                if name_el is not None and name_el.text
            ]

            year = None
            if published_el is not None and published_el.text:
                try:
                    year = int(published_el.text[:4])
                except ValueError:
                    year = None

            abstract = _clean_text(summary_el.text) if summary_el is not None else None
            url = id_el.text.strip() if id_el is not None and id_el.text else None

            categories = [
                cat.get("term") for cat in entry.findall(f"{ATOM_NS}category") if cat.get("term")
            ]
            primary_category_el = entry.find(f"{ARXIV_NS}primary_category")
            domain = primary_category_el.get("term") if primary_category_el is not None else None

            records.append({
                "title": title,
                "authors": authors,
                "year": year,
                "abstract": abstract,
                "url": url,
                "domain": domain,
                "categories": categories,
            })

        return records

    def _map_to_raw_article(self, record: dict, keyword: str) -> RawArticle:
        return RawArticle(
            source=SourceEnum.ARXIV,
            search_keyword=keyword,
            collection_date=datetime.now(timezone.utc),
            title=record["title"],
            authors=record["authors"],
            year=record["year"],
            abstract=record["abstract"],
            url=record["url"],
            domain=record["domain"],
            categories=record["categories"],
        )

    async def health_check(self) -> bool:
        try:
            response = await self._client.get(
                ARXIV_API_URL, params={"search_query": "all:test", "max_results": 1}
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
