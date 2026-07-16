import asyncio
import time
from datetime import datetime, timezone
from xml.etree import ElementTree

import httpx

from app.connectors.base import BaseConnector
from app.domain.entities import RawArticle
from app.domain.exceptions import ConnectorError

ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"

ARXIV_API_URL = "https://export.arxiv.org/api/query"
MIN_SECONDS_BETWEEN_REQUESTS = 3.0


class ArxivConnector(BaseConnector):
    """
    arXiv connector (M04 - Must Have).
    Docs: https://arxiv.org/help/api/user-manual
    Rate limit per arXiv's own guidance: ~1 request every 3 seconds.
    """

    name = "arxiv"

    def __init__(self, http_client: httpx.AsyncClient | None = None, timeout: float = 30.0):
        self._client = http_client
        self._timeout = timeout
        self._last_request_at: float | None = None
        self._rate_limit_lock = asyncio.Lock()

    async def _respect_rate_limit(self) -> None:
        async with self._rate_limit_lock:
            if self._last_request_at is not None:
                elapsed = time.monotonic() - self._last_request_at
                wait = MIN_SECONDS_BETWEEN_REQUESTS - elapsed
                if wait > 0:
                    await asyncio.sleep(wait)
            self._last_request_at = time.monotonic()

    async def search(
        self,
        keyword: str,
        max_results: int = 10,
        filters: dict | None = None,
    ) -> list[RawArticle]:
        if not keyword or not keyword.strip():
            raise ConnectorError(self.name, "Keyword must not be empty.")
        if max_results < 1:
            raise ConnectorError(self.name, "max_results must be at least 1.")

        await self._respect_rate_limit()

        params = {
            "search_query": f"all:{keyword}",
            "start": 0,
            "max_results": max_results,
        }

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout, follow_redirects=True)
        try:
            try:
                response = await client.get(ARXIV_API_URL, params=params)
            except httpx.RequestError as exc:
                raise ConnectorError(
                    self.name, f"Network error while querying arXiv: {exc}"
                ) from exc
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code != 200:
            raise ConnectorError(
                self.name,
                f"arXiv returned HTTP {response.status_code} for keyword '{keyword}'.",
            )

        try:
            return self._parse_feed(response.text, keyword)
        except ElementTree.ParseError as exc:
            raise ConnectorError(self.name, f"Could not parse arXiv response: {exc}") from exc

    def _parse_feed(self, xml_text: str, keyword: str) -> list[RawArticle]:
        root = ElementTree.fromstring(xml_text)
        collected_at = datetime.now(timezone.utc)
        articles: list[RawArticle] = []

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

            articles.append(
                RawArticle(
                    title=title,
                    authors=authors,
                    year=year,
                    abstract=abstract,
                    url=url,
                    domain=domain,
                    categories=categories,
                    source=self.name,
                    search_keyword=keyword,
                    collection_date=collected_at,
                )
            )

        return articles


def _clean_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.split())
