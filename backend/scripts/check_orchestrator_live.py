"""
One-off manual sanity check of the orchestrator fan-out (US-03.4) against the
real arXiv + OpenAlex APIs. Not part of the test suite - run directly:
    docker compose exec backend python scripts/check_orchestrator_live.py
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.connectors.arxiv import ArxivConnector
from app.connectors.openalex import OpenAlexConnector
from app.orchestrator.runner import run_collection
from app.orchestrator.state import create_state

KEYWORDS = ["machine learning", "climate change"]
SOURCES = ["arxiv", "openalex"]
MAX_ARTICLES_PER_KEYWORD = 5

CONNECTOR_FACTORIES = {
    "arxiv": lambda: ArxivConnector(),
    "openalex": lambda: OpenAlexConnector(polite_pool_email=settings.polite_pool_email),
}


async def main():
    state = create_state("COL-LIVE", keywords=KEYWORDS, sources=SOURCES)
    print(f"Starting fan-out: {len(KEYWORDS)} keywords x {len(SOURCES)} sources...\n")

    async def report_progress():
        while state.overall_progress < 100.0:
            print(
                f"  [{state.elapsed_seconds}s] {state.overall_progress:.0f}% - "
                f"current keyword: {state.current_keyword}"
            )
            await asyncio.sleep(1)

    started = time.monotonic()
    reporter = asyncio.create_task(report_progress())
    articles = await run_collection(
        state,
        connector_factories=CONNECTOR_FACTORIES,
        max_articles_per_keyword=MAX_ARTICLES_PER_KEYWORD,
    )
    reporter.cancel()

    print(f"\nDone in {time.monotonic() - started:.1f}s - {len(articles)} articles total\n")
    for source, progress in state.source_progress.items():
        print(f"  {source}: status={progress.status} articles_fetched={progress.articles_fetched} "
              f"detail={progress.detail}")
    print(f"\noverall_progress={state.overall_progress}  warning={state.warning}  error={state.error}")


if __name__ == "__main__":
    asyncio.run(main())
