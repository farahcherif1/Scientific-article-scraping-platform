"""
Crossref connector (US-03.3) — follows the same shared-infra structure as
ArxivConnector (US-03.1) and OpenAlexConnector (US-03.2): the resilient HTTP
layer (US-03.6, retries on 5xx/429/network errors with exponential backoff),
the shared per-source rate limiter, and the in-memory response cache.

Docs: https://api.crossref.org/swagger-ui/index.html
Rate limit: 50 req/s in the polite pool (see §3.1). Every request identifies
the platform via a User-Agent + mailto, per the Collection Charter
(Appendix B.2, rule 7).

NOTE: Crossref's "type" field (e.g. "journal-article", "proceedings-article")
is fetched but currently has nowhere to go - RawArticle does not have a
document_type field. Flag with whoever owns app/domain/entities.py if that
field needs to come back (it's an explicit deliverable in Tâche 3.3).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings
from app.connectors.base import BaseConnector
from app.domain.entities import ConnectorError, RawArticle, SourceEnum
from app.infra.cache import get_cached, set_cached
from app.infra.retries import call_with_retry
from app.orchestrator.rate_limiter import CROSSREF_RATE_LIMITER

CROSSREF_API_URL = "https://api.crossref.org/works"

_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/.+$")


def normalize_doi(raw_doi: str | None) -> str | None:
    """
    Normalize a DOI: strip the https://doi.org/ prefix if present, lowercase
    it, and validate against the standard DOI pattern (see Appendix A).
    Returns None if the input doesn't look like a valid DOI.
    """
    if not raw_doi:
        return None
    candidate = raw_doi.strip()
    candidate = re.sub(r"^https?://(dx\.)?doi\.org/", "", candidate, flags=re.IGNORECASE)
    candidate = candidate.lower()
    if _DOI_PATTERN.match(candidate):
        return candidate
    return None


class CrossrefConnector(BaseConnector):
    name = "crossref"

    def __init__(
        self,
        *,
        http_client: Optional[httpx.AsyncClient] = None,
        rate_limiter=CROSSREF_RATE_LIMITER,
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

    def _polite_headers(self) -> dict[str, str]:
        return {
            "User-Agent": f"Team08-E26-Yonnovia/1.0 (mailto:{settings.polite_pool_email})",
        }

    async def search(
        self,
        keyword: str,
        max_results: int = 10,
        filters: dict | None = None,
    ) -> list[RawArticle]:
        if not keyword or not keyword.strip():
            raise ConnectorError(
                source=SourceEnum.CROSSREF,
                endpoint=CROSSREF_API_URL,
                keyword=keyword,
                error_class="InvalidInput",
                message="Keyword must not be empty.",
            )
        if max_results < 1:
            raise ConnectorError(
                source=SourceEnum.CROSSREF,
                endpoint=CROSSREF_API_URL,
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
            "rows": max_results,
            "mailto": settings.polite_pool_email,
        }

        await self._rate_limiter.acquire()

        async def _do_request(p=params):
            return await self._client.get(
                CROSSREF_API_URL, params=p, headers=self._polite_headers()
            )

        response = await call_with_retry(
            _do_request,
            source=self.name,
            endpoint=CROSSREF_API_URL,
            keyword=keyword,
        )

        if response.status_code != 200:
            raise ConnectorError(
                source=SourceEnum.CROSSREF,
                endpoint=CROSSREF_API_URL,
                keyword=keyword,
                error_class=f"HTTP{response.status_code}",
                message=f"Crossref returned HTTP {response.status_code} for keyword '{keyword}'.",
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorError(
                source=SourceEnum.CROSSREF,
                endpoint=CROSSREF_API_URL,
                keyword=keyword,
                error_class="ParseError",
                message=f"Could not parse Crossref response: {exc}",
            ) from exc

        items = payload.get("message", {}).get("items", [])
        raw_records = [self._parse_item(item) for item in items]

        set_cached(self.name, keyword, cache_params, raw_records)
        return [self._map_to_raw_article(record, keyword) for record in raw_records]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_item(self, item: dict) -> dict:
        title_list = item.get("title") or []
        title = _clean_text(title_list[0]) if title_list else ""

        authors = []
        for author in item.get("author", []) or []:
            given = (author.get("given") or "").strip()
            family = (author.get("family") or "").strip()
            full_name = " ".join(part for part in [given, family] if part)
            if full_name:
                authors.append(full_name)

        year = None
        date_parts = item.get("issued", {}).get("date-parts", [])
        if date_parts and date_parts[0]:
            year = date_parts[0][0]

        doi = normalize_doi(item.get("DOI"))

        container_titles = item.get("container-title") or []
        venue = container_titles[0] if container_titles else item.get("publisher")

        abstract = item.get("abstract")
        if abstract:
            abstract = _strip_jats_tags(abstract)

        return {
            "title": title,
            "authors": authors,
            "year": year,
            "abstract": abstract,
            "url": item.get("URL"),
            "doi": doi,
            "venue": venue,
            "citation_count": item.get("is-referenced-by-count"),
        }

    def _map_to_raw_article(self, record: dict, keyword: str) -> RawArticle:
        return RawArticle(
            source=SourceEnum.CROSSREF,
            search_keyword=keyword,
            collection_date=datetime.now(timezone.utc),
            title=record["title"],
            authors=record["authors"],
            year=record["year"],
            abstract=record["abstract"],
            url=record["url"],
            doi=record["doi"],
            venue=record["venue"],
            citation_count=record["citation_count"],
        )

    async def health_check(self) -> bool:
        try:
            response = await self._client.get(
                CROSSREF_API_URL,
                params={"query": "test", "rows": 1, "mailto": settings.polite_pool_email},
                headers=self._polite_headers(),
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


def _strip_jats_tags(value: str) -> str:
    """Crossref abstracts are sometimes wrapped in JATS XML tags (<jats:p>...)."""
    return _clean_text(re.sub(r"<[^>]+>", " ", value))
