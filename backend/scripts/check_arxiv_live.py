"""
One-off manual sanity check against the real arXiv API.
Not part of the test suite - run directly:
    docker compose exec backend python scripts/check_arxiv_live.py
"""

import asyncio
import sys
from pathlib import Path

# Ensure the backend root (/app) is on sys.path so `app.*` imports resolve
# regardless of the current working directory this script is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.connectors.arxiv import ArxivConnector


async def main():
    connector = ArxivConnector()
    print("Querying arXiv for 'large language models' (max_results=5)...\n")

    results = await connector.search("large language models", max_results=5)

    print(f"Got {len(results)} articles\n")
    for i, article in enumerate(results, start=1):
        print(f"--- Article {i} ---")
        print(f"Title:      {article.title}")
        print(f"Authors:    {', '.join(article.authors)}")
        print(f"Year:       {article.year}")
        print(f"URL:        {article.url}")
        print(f"Domain:     {article.domain}")
        print(f"Categories: {article.categories}")
        print(f"Abstract:   {article.abstract[:150]}..." if article.abstract else "Abstract:   None")
        print()


if __name__ == "__main__":
    asyncio.run(main())
