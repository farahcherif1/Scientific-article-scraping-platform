"""
Multi-source orchestrator fan-out loop (US-03.4 T-03.4.2).

Sources run concurrently (`asyncio.gather`) so one slow or failing source
never blocks the others; within a source, keywords run sequentially (the
shared per-source rate limiter, T-03.4.3, already serializes requests there
anyway). A source with no registered connector - or whose connector raises
ConnectorError for every keyword - is recorded as failed and the run
continues with whatever else is selected, per the story's AC.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Protocol

from app.connectors.base import SearchFilters
from app.domain.compliance import enforce_max_articles_per_keyword
from app.domain.entities import ConnectorError, RawArticle
from app.orchestrator.state import CollectionState

logger = logging.getLogger("app.orchestrator.runner")


class SearchableConnector(Protocol):
    async def search(
        self, keyword: str, max_results: int, filters: SearchFilters | None = None
    ) -> list[RawArticle]: ...

    async def aclose(self) -> None: ...


ConnectorFactory = Callable[[], SearchableConnector]


async def run_collection(
    state: CollectionState,
    *,
    connector_factories: dict[str, ConnectorFactory],
    max_articles_per_keyword: int,
    filters: SearchFilters | None = None,
) -> list[RawArticle]:
    """
    Runs the keyword x source fan-out for `state`, mutating its progress
    fields as it goes, and returns the collected, compliance-cap-enforced
    articles (US-03.7).
    """
    collected: list[RawArticle] = []

    async def run_source(source: str) -> None:
        progress = state.source_progress[source]
        factory = connector_factories.get(source)
        if factory is None:
            progress.status = "failed"
            progress.detail = f"'{source}' connector is not implemented yet."
            logger.warning(
                "source_not_implemented",
                extra={"source": source, "collection_id": state.id},
            )
            state.completed_pairs += len(state.keywords)
            return

        connector = factory()
        progress.status = "running"
        any_success = False
        try:
            for keyword in state.keywords:
                if state.abort_requested:
                    break
                state.current_keyword = keyword
                try:
                    articles = await connector.search(keyword, max_articles_per_keyword, filters)
                    collected.extend(articles)
                    progress.articles_fetched += len(articles)
                    any_success = True
                except ConnectorError as exc:
                    logger.error(
                        "source_keyword_failed",
                        extra={
                            "source": source,
                            "keyword": keyword,
                            "error_class": exc.error_class,
                            "collection_id": state.id,
                        },
                    )
                    progress.detail = f"'{keyword}' failed: {exc.error_class}"
                finally:
                    state.completed_pairs += 1
        finally:
            if state.abort_requested:
                progress.status = "failed"
                progress.detail = progress.detail or "Aborted."
            elif not state.keywords or any_success:
                progress.status = "done"
            else:
                progress.status = "failed"
                progress.detail = progress.detail or "All keywords failed for this source."
            await connector.aclose()

    await asyncio.gather(*(run_source(source) for source in state.sources))

    cap_result = enforce_max_articles_per_keyword(collected, max(max_articles_per_keyword, 1))
    if cap_result.cap_was_hit:
        capped = ", ".join(f"{source}/{keyword}" for source, keyword in cap_result.capped_groups)
        state.warning = f"Compliance cap ({max_articles_per_keyword}/keyword) enforced for: {capped}."

    return cap_result.articles
