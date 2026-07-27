"""
GenericConnector - config-driven connector for "Custom Connector" sources
(EP-custom-connectors). Implements the same `BaseConnector` contract as the
five built-in connectors (arxiv/crossref/openalex/pubmed/semantic_scholar),
which are complete and are NOT touched by this feature - this is a new,
separate connector that a researcher configures instead of one we hardcode.

Every behavior that varies across real sources (auth, pagination, field
mapping - see docs/custom-connectors.md for the research behind this) is
driven entirely by `CustomConnectorConfig` (app/connectors/generic_config.py)
instead of source-specific code, so adding IEEE Xplore, HAL, DOAJ, CORE,
Europe PMC, or an institutional repository is a configuration exercise, not
a new connector file.

Reuses the same shared infrastructure the built-in connectors use:
  - `app.infra.retries.call_with_retry` - resilient HTTP layer (US-03.6):
    retries only on 5xx/429/network errors, exponential backoff, max 2
    retries, raises ConnectorError on persistent failure so the orchestrator
    logs-and-continues instead of crashing (US-03.4).
  - `app.orchestrator.rate_limiter.AsyncRateLimiter` - same leaky-bucket
    limiter class the built-ins use, one instance per configured connector
    (rate from the researcher's `rate_limit_rps` config value).
  - `app.connectors.crossref.normalize_doi` - the same DOI normalization
    PubMed and Semantic Scholar already reuse rather than reimplementing.
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import settings
from app.connectors.base import BaseConnector, SearchFilters
from app.connectors.crossref import normalize_doi
from app.connectors.generic_config import (
    AuthType,
    CustomConnectorConfig,
    PaginationStyle,
    resolve_path,
)
from app.domain.entities import RawArticle
from app.infra.retries import call_with_retry
from app.orchestrator.rate_limiter import AsyncRateLimiter

logger = logging.getLogger("app.connectors.generic")

# Hard ceiling on pagination round-trips per keyword, independent of
# max_results - a defensive backstop against a misconfigured cursor/offset
# that never terminates (e.g. next_cursor_path pointing at a field that
# never goes empty). Compliance's own 100-article cap makes this generous.
_MAX_PAGES_PER_SEARCH = 25


class GenericConnector(BaseConnector):
    """
    One instance = one configured custom source. `name` (required by
    BaseConnector) is the connector's persisted slug, so orchestrator logs,
    ConnectorError, and RawArticle.source all read the same identifier the
    researcher chose - no special-casing downstream.
    """

    def __init__(
        self,
        *,
        slug: str,
        config: CustomConnectorConfig,
        http_client: httpx.AsyncClient | None = None,
        rate_limiter: AsyncRateLimiter | None = None,
        polite_pool_email: str | None = None,
    ):
        self.name = slug
        self._config = config
        self._polite_pool_email = polite_pool_email or settings.polite_pool_email
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=config.connect_timeout_s,
                read=config.read_timeout_s,
                write=config.read_timeout_s,
                pool=config.read_timeout_s,
            ),
        )
        self._rate_limiter = rate_limiter or AsyncRateLimiter(1 / config.rate_limit_rps)

    async def search(
        self,
        keyword: str,
        max_results: int,
        filters: SearchFilters | None = None,
    ) -> list[RawArticle]:
        filters = filters or SearchFilters()
        pagination = self._config.pagination

        articles: list[RawArticle] = []
        collected = 0
        page = pagination.start_page
        offset = pagination.start_offset
        cursor: str | None = None

        for _ in range(_MAX_PAGES_PER_SEARCH):
            if collected >= max_results:
                break
            page_size = min(pagination.page_size, max_results - collected)
            params = self._build_params(
                keyword, filters, page=page, offset=offset, cursor=cursor, page_size=page_size
            )
            headers = self._build_headers()

            await self._rate_limiter.acquire()

            async def _do_request(p=params, h=headers):
                if self._config.http_method == "POST":
                    return await self._client.post(self._config.base_url, params=p, headers=h)
                return await self._client.get(self._config.base_url, params=p, headers=h)

            response = await call_with_retry(
                _do_request,
                source=self.name,
                endpoint=self._config.base_url,
                keyword=keyword,
            )
            payload = response.json()

            results = resolve_path(payload, pagination.results_path)
            if results is None:
                results = []
            elif not isinstance(results, list):
                results = [results]

            for record in results:
                if collected >= max_results:
                    break
                if not isinstance(record, dict):
                    continue
                articles.append(self._map_to_raw_article(record, keyword))
                collected += 1

            if pagination.style == PaginationStyle.NONE or not results:
                break
            if pagination.stop_when_empty and len(results) < page_size:
                break
            if pagination.total_path:
                total = resolve_path(payload, pagination.total_path)
                if isinstance(total, int | float) and collected >= total:
                    break

            if pagination.style == PaginationStyle.PAGE:
                page += 1
            elif pagination.style == PaginationStyle.OFFSET:
                offset += page_size
            elif pagination.style == PaginationStyle.CURSOR:
                cursor = resolve_path(payload, pagination.next_cursor_path)
                if not cursor:
                    break

        return articles

    async def test_connection(self, keyword: str, max_results: int) -> dict[str, Any]:
        """
        Performs exactly one request (no pagination loop) and returns the
        request URL, status code, raw parsed response body, and the
        RawArticle records the current field mapping produces from it - so
        the wizard's "test connection" step can show a researcher mapping
        mismatches before they save the connector. Raises ConnectorError on
        failure, same as `search()` (the API layer turns that into a
        `success: false` response instead of a 500).
        """
        page_size = min(self._config.pagination.page_size, max_results)
        params = self._build_params(
            keyword,
            SearchFilters(),
            page=self._config.pagination.start_page,
            offset=self._config.pagination.start_offset,
            cursor=None,
            page_size=page_size,
        )
        headers = self._build_headers()

        await self._rate_limiter.acquire()

        async def _do_request(p=params, h=headers):
            if self._config.http_method == "POST":
                return await self._client.post(self._config.base_url, params=p, headers=h)
            return await self._client.get(self._config.base_url, params=p, headers=h)

        response = await call_with_retry(
            _do_request,
            source=self.name,
            endpoint=self._config.base_url,
            keyword=keyword,
        )
        payload = response.json()

        results = resolve_path(payload, self._config.pagination.results_path)
        if results is None:
            results = []
        elif not isinstance(results, list):
            results = [results]
        results = results[:max_results]

        mapped = [
            self._map_to_raw_article(record, keyword)
            for record in results
            if isinstance(record, dict)
        ]

        return {
            "status_code": response.status_code,
            "request_url": str(response.request.url),
            "raw_response": payload,
            "sample_records": results,
            "mapped_articles": mapped,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_params(
        self,
        keyword: str,
        filters: SearchFilters,
        *,
        page: int,
        offset: int,
        cursor: str | None,
        page_size: int,
    ) -> dict[str, Any]:
        qm = self._config.query_mapping
        pagination = self._config.pagination
        params: dict[str, Any] = dict(qm.static_params)
        params[qm.keyword_param] = keyword

        if qm.year_from_param and filters.year_from:
            params[qm.year_from_param] = filters.year_from
        if qm.year_to_param and filters.year_to:
            params[qm.year_to_param] = filters.year_to

        if pagination.page_size_param:
            params[pagination.page_size_param] = page_size

        if pagination.style == PaginationStyle.PAGE and pagination.page_param:
            params[pagination.page_param] = page
        elif pagination.style == PaginationStyle.OFFSET and pagination.offset_param:
            params[pagination.offset_param] = offset
        elif pagination.style == PaginationStyle.CURSOR and pagination.cursor_param and cursor:
            params[pagination.cursor_param] = cursor

        auth = self._config.auth
        if auth.type == AuthType.API_KEY_QUERY_PARAM and auth.key_name:
            params[auth.key_name] = auth.key_value

        return params

    def _build_headers(self) -> dict[str, str]:
        headers = dict(self._config.headers)
        # Compliance charter rule 7 applies to every outbound call this
        # platform makes, custom sources included: identify ourselves even
        # when the source doesn't require it.
        headers.setdefault(
            "User-Agent", f"Team08-E26-Yonnovia/1.0 (mailto:{self._polite_pool_email})"
        )
        auth = self._config.auth
        if auth.type == AuthType.API_KEY_HEADER and auth.key_name:
            headers[auth.key_name] = auth.key_value or ""
        return headers

    def _map_to_raw_article(self, record: dict, keyword: str) -> RawArticle:
        fm = self._config.field_mapping

        def _get(mapping) -> Any:
            value = resolve_path(record, mapping.path) if mapping.path else None
            return value if value is not None else mapping.default

        return RawArticle(
            source=self.name,
            search_keyword=keyword,
            collection_date=datetime.now(UTC),
            title=_coerce_str(_get(fm.title)) or "",
            authors=_coerce_str_list(_get(fm.authors)),
            year=_coerce_int(_get(fm.year)),
            abstract=_coerce_str(_get(fm.abstract)),
            doi=normalize_doi(_coerce_str(_get(fm.doi))),
            venue=_coerce_str(_get(fm.venue)),
            citation_count=_coerce_int(_get(fm.citation_count)),
            url=_coerce_str(_get(fm.url)),
        )

    async def health_check(self) -> bool:
        try:
            params = self._build_params(
                "test",
                SearchFilters(),
                page=self._config.pagination.start_page,
                offset=self._config.pagination.start_offset,
                cursor=None,
                page_size=1,
            )
            headers = self._build_headers()
            if self._config.http_method == "POST":
                response = await self._client.post(
                    self._config.base_url, params=params, headers=headers
                )
            else:
                response = await self._client.get(
                    self._config.base_url, params=params, headers=headers
                )
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v not in (None, "") and str(v).strip()]
    text = _coerce_str(value)
    return [text] if text else []


_LEADING_INT = re.compile(r"-?\d+")


def _coerce_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        match = _LEADING_INT.match(value.strip())
        if match:
            return int(match.group())
    return None
