"""
OpenAlex connector — US-03.2.

Acceptance criteria implemented:
  - Every request sends the polite-pool `mailto=` parameter.
  - cited_by_count -> citation_count ; concepts -> domain.
  - Cursor pagination stops cleanly at max_results (no over-fetching).
  - HTTP 429 triggers exponential backoff, max 2 retries (via
    app.infra.retries.call_with_retry, shared resilient HTTP layer).

"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.connectors.base import BaseConnector, SearchFilters
from app.domain.entities import ConnectorError, RawArticle, SourceEnum
from app.infra.cache import get_cached, set_cached
from app.infra.retries import call_with_retry
from app.orchestrator.rate_limiter import OPENALEX_RATE_LIMITER

logger = logging.getLogger("app.connectors.openalex")

OPENALEX_BASE_URL = "https://api.openalex.org/works"
DEFAULT_PAGE_SIZE = 25  # OpenAlex per-page cap is 200; keep requests modest


class OpenAlexConnector(BaseConnector):
    name = "openalex"

    def __init__(
        self,
        *,
        polite_pool_email: str,
        http_client: Optional[httpx.AsyncClient] = None,
        rate_limiter=OPENALEX_RATE_LIMITER,
        connect_timeout_s: float = 10.0,
        read_timeout_s: float = 30.0,
    ):
        """
        polite_pool_email: required config value (POLITE_POOL_EMAIL in .env).
        Not a secret — used to identify the platform per OpenAlex's polite
        pool policy (Appendix B, rule 7).
        """
        self._email = polite_pool_email
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(connect=connect_timeout_s, read=read_timeout_s,
                                   write=read_timeout_s, pool=read_timeout_s),
            headers={"User-Agent": "Team08-E26-Yonnovia/1.0 (mailto:%s)" % polite_pool_email},
        )
        self._rate_limiter = rate_limiter

    async def search(
        self,
        keyword: str,
        max_results: int,
        filters: Optional[SearchFilters] = None,
    ) -> list[RawArticle]:
        filters = filters or SearchFilters()
        cache_params = {
            "max_results": max_results,
            "year_from": filters.year_from,
            "year_to": filters.year_to,
        }

        cached = get_cached(self.name, keyword, cache_params)
        if cached is not None:
            logger.info("cache_hit", extra={"source": self.name, "keyword": keyword})
            return [self._map_to_raw_article(item, keyword) for item in cached]

        raw_records: list[dict] = []
        articles: list[RawArticle] = []
        cursor = "*"
        collected = 0

        try:
            while collected < max_results:
                page_size = min(DEFAULT_PAGE_SIZE, max_results - collected)
                params = self._build_params(keyword, filters, cursor, page_size)

                await self._rate_limiter.acquire()

                async def _do_request(p=params):
                    return await self._client.get(OPENALEX_BASE_URL, params=p)

                response = await call_with_retry(
                    _do_request,
                    source=self.name,
                    endpoint=OPENALEX_BASE_URL,
                    keyword=keyword,
                )
                payload = response.json()

                results = payload.get("results", [])
                if not results:
                    break

                for record in results:
                    if collected >= max_results:
                        break
                    raw_records.append(record)
                    articles.append(self._map_to_raw_article(record, keyword))
                    collected += 1

                cursor = payload.get("meta", {}).get("next_cursor")
                if not cursor:
                    break  # no more pages

        except ConnectorError:
            # Per US-03.4: one source failing must not block the others.
            # Re-raise so the orchestrator can log-and-continue; do NOT
            # swallow silently here — the orchestrator decides that policy.
            raise

        set_cached(self.name, keyword, cache_params, raw_records)
        return articles

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_params(
        self,
        keyword: str,
        filters: SearchFilters,
        cursor: str,
        page_size: int,
    ) -> dict:
        params: dict = {
            "search": keyword,
            "per_page": page_size,
            "cursor": cursor,
            "mailto": self._email,  # polite pool — required on every request
        }
        year_filters = []
        if filters.year_from:
            year_filters.append(f"from_publication_date:{filters.year_from}-01-01")
        if filters.year_to:
            year_filters.append(f"to_publication_date:{filters.year_to}-12-31")
        if year_filters:
            params["filter"] = ",".join(year_filters)
        return params

    def _map_to_raw_article(self, record: dict, keyword: str) -> RawArticle:
        """OpenAlex field mapping per US-03.2 acceptance criteria."""
        doi = record.get("doi")
        if doi and doi.startswith("https://doi.org/"):
            doi = doi.removeprefix("https://doi.org/")

        authors_raw = [
            a.get("author", {}).get("display_name")
            for a in record.get("authorships", [])
            if a.get("author", {}).get("display_name")
        ]

        concepts = record.get("concepts", [])
        domain = concepts[0]["display_name"] if concepts else None

        venue = None
        primary_location = record.get("primary_location")
        if primary_location:
            # `source` is a present-but-null key (not just absent) when
            # OpenAlex hasn't identified a venue for the work - seen live.
            source = primary_location.get("source")
            if source:
                venue = source.get("display_name")

        abstract = self._reconstruct_abstract(record.get("abstract_inverted_index"))

        return RawArticle(
            source=SourceEnum.OPENALEX,
            search_keyword=keyword,
            collection_date=datetime.now(timezone.utc),
            title=record.get("title") or record.get("display_name") or "",
            authors=authors_raw,
            year=record.get("publication_year"),
            abstract=abstract,
            doi=doi.lower() if doi else None,
            venue=venue,
            citation_count=record.get("cited_by_count"),  # -> citation_count
            url=record.get("id"),
            domain=domain,  # concepts -> domain
        )

    @staticmethod
    def _reconstruct_abstract(inverted_index: Optional[dict]) -> Optional[str]:
        """
        OpenAlex returns abstracts as an inverted index (word -> [positions])
        instead of plain text (contractual quirk of the source). Reconstruct
        the original word order.
        """
        if not inverted_index:
            return None
        position_to_word: dict[int, str] = {}
        for word, positions in inverted_index.items():
            for pos in positions:
                position_to_word[pos] = word
        if not position_to_word:
            return None
        return " ".join(position_to_word[i] for i in sorted(position_to_word))

    async def health_check(self) -> bool:
        try:
            response = await self._client.get(
                OPENALEX_BASE_URL, params={"per_page": 1, "mailto": self._email}
            )
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()