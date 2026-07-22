"""
One-off manual sanity check against the real PubMed E-utilities API.
Not part of the test suite - run directly:
    docker compose exec backend python scripts/check_pubmed_live.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.connectors.pubmed import PubMedConnector


async def main():
    connector = PubMedConnector()
    print("Querying PubMed for 'covid vaccine' (max_results=5)...\n")

    results = await connector.search("covid vaccine", max_results=5)

    print(f"Got {len(results)} articles\n")
    with_doi = sum(1 for a in results if a.doi)
    if results:
        print(f"DOI coverage: {with_doi}/{len(results)} ({100 * with_doi / len(results):.0f}%)\n")

    for i, article in enumerate(results, start=1):
        print(f"--- Article {i} ---")
        print(f"Title:      {article.title}")
        print(f"Authors:    {', '.join(article.authors)}")
        print(f"Year:       {article.year}")
        print(f"DOI:        {article.doi}")
        print(f"Venue:      {article.venue}")
        print(f"URL:        {article.url}")
        print(f"Abstract:   {'present' if article.abstract else 'missing'}")
        print()

    await connector.aclose()


if __name__ == "__main__":
    asyncio.run(main())
