"""
Semantic Scholar connector (Graph API) — reintroduces the source that was
previously dropped as a schema-only placeholder with no implementation (see
docs/limitations.md), now with a real implementation. Follows the same
shared-infra structure as the other connectors: the resilient HTTP layer
(US-03.6, retries on 5xx/429/network errors with exponential backoff), the
shared per-source rate limiter, and the in-memory response cache.

Docs: https://api.semanticscholar.org/api-docs/graph
Auth: none required. Unauthenticated requests share a low-throughput public
pool, so the connector defaults to a conservative rate limit
(settings.rate_limit_semantic_scholar_rps, ~1 req/s). An optional API key
(settings.semantic_scholar_api_key) is sent as the `x-api-key` header when
configured, for a faster limit — not required to run.
"""
from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.config import settings
from app.connectors.base import BaseConnector
from app.connectors.crossref import normalize_doi
from app.domain.entities import ConnectorError, RawArticle, SourceEnum
from app.infra.cache import get_cached, set_cached
from app.infra.retries import call_with_retry
from app.orchestrator.rate_limiter import SEMANTIC_SCHOLAR_RATE_LIMITER

SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

FIELDS = "title,abstract,year,venue,authors,externalIds,citationCount,fieldsOfStudy,url"


class SemanticScholarConnector(BaseConnector):
    name = "semantic_scholar"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        rate_limiter=SEMANTIC_SCHOLAR_RATE_LIMITER,
        connect_timeout_s: float = 10.0,
        read_timeout_s: float = 30.0,
    ):
        self._api_key = api_key if api_key is not None else settings.semantic_scholar_api_key
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=connect_timeout_s, read=read_timeout_s,
                write=read_timeout_s, pool=read_timeout_s,
            ),
            follow_redirects=True,
        )
        self._rate_limiter = rate_limiter

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self._api_key} if self._api_key else {}

    async def search(
        self,
        keyword: str,
        max_results: int = 10,
        filters: dict | None = None,
    ) -> list[RawArticle]:
        if not keyword or not keyword.strip():
            raise ConnectorError(
                source=SourceEnum.SEMANTIC_SCHOLAR,
                endpoint=SEMANTIC_SCHOLAR_API_URL,
                keyword=keyword,
                error_class="InvalidInput",
                message="Keyword must not be empty.",
            )
        if max_results < 1:
            raise ConnectorError(
                source=SourceEnum.SEMANTIC_SCHOLAR,
                endpoint=SEMANTIC_SCHOLAR_API_URL,
                keyword=keyword,
                error_class="InvalidInput",
                message="max_results must be at least 1.",
            )

        cache_params = {"max_results": max_results}
        cached = get_cached(self.name, keyword, cache_params)
        if cached is not None:
            return [self._map_to_raw_article(record, keyword) for record in cached]

        params = {
            "query": keyword,
            # Graph API caps `limit` at 100 regardless of what's requested.
            "limit": min(max_results, 100),
            "fields": FIELDS,
        }

        await self._rate_limiter.acquire()

        async def _do_request(p=params):
            return await self._client.get(
                SEMANTIC_SCHOLAR_API_URL, params=p, headers=self._headers()
            )

        response = await call_with_retry(
            _do_request,
            source=self.name,
            endpoint=SEMANTIC_SCHOLAR_API_URL,
            keyword=keyword,
        )

        if response.status_code != 200:
            raise ConnectorError(
                source=SourceEnum.SEMANTIC_SCHOLAR,
                endpoint=SEMANTIC_SCHOLAR_API_URL,
                keyword=keyword,
                error_class=f"HTTP{response.status_code}",
                message=f"Semantic Scholar returned HTTP {response.status_code} for keyword '{keyword}'.",
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorError(
                source=SourceEnum.SEMANTIC_SCHOLAR,
                endpoint=SEMANTIC_SCHOLAR_API_URL,
                keyword=keyword,
                error_class="ParseError",
                message=f"Could not parse Semantic Scholar response: {exc}",
            ) from exc

        items = payload.get("data") or []
        raw_records = [self._parse_item(item) for item in items[:max_results]]

        set_cached(self.name, keyword, cache_params, raw_records)
        return [self._map_to_raw_article(record, keyword) for record in raw_records]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_item(self, item: dict) -> dict:
        authors = [
            author.get("name") for author in (item.get("authors") or []) if author.get("name")
        ]

        fields_of_study = item.get("fieldsOfStudy") or []
        domain = fields_of_study[0] if fields_of_study else None

        external_ids = item.get("externalIds") or {}
        doi = normalize_doi(external_ids.get("DOI"))

        return {
            "title": _clean_text(item.get("title")),
            "authors": authors,
            "year": item.get("year"),
            "abstract": item.get("abstract"),
            "url": item.get("url"),
            "doi": doi,
            "venue": item.get("venue") or None,
            "domain": domain,
            "categories": fields_of_study,
            "citation_count": item.get("citationCount"),
        }

    def _map_to_raw_article(self, record: dict, keyword: str) -> RawArticle:
        return RawArticle(
            source=SourceEnum.SEMANTIC_SCHOLAR,
            search_keyword=keyword,
            collection_date=datetime.now(UTC),
            title=record["title"],
            authors=record["authors"],
            year=record["year"],
            abstract=record["abstract"],
            url=record["url"],
            doi=record["doi"],
            venue=record["venue"],
            domain=record["domain"],
            categories=record["categories"],
            citation_count=record["citation_count"],
        )

    async def health_check(self) -> bool:
        try:
            response = await self._client.get(
                SEMANTIC_SCHOLAR_API_URL,
                params={"query": "test", "limit": 1, "fields": "title"},
                headers=self._headers(),
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
