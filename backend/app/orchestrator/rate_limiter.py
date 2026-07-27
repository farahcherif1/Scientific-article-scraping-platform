"""Per-source rate limiters (US-03.4 T-03.4.3), one shared instance per source."""
from __future__ import annotations

import asyncio
import time

from app.config import settings


class AsyncRateLimiter:
    """Enforces a minimum interval between successive requests (leaky bucket of size 1)."""

    def __init__(self, min_interval_s: float):
        self._min_interval_s = min_interval_s
        self._lock = asyncio.Lock()
        self._last_call: float | None = None

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._last_call is not None:
                wait_s = self._min_interval_s - (now - self._last_call)
                if wait_s > 0:
                    await asyncio.sleep(wait_s)
            self._last_call = time.monotonic()


OPENALEX_RATE_LIMITER = AsyncRateLimiter(1 / settings.rate_limit_openalex_rps)
ARXIV_RATE_LIMITER = AsyncRateLimiter(settings.rate_limit_arxiv_interval_s)
CROSSREF_RATE_LIMITER = AsyncRateLimiter(1 / settings.rate_limit_crossref_rps)
PUBMED_RATE_LIMITER = AsyncRateLimiter(1 / settings.rate_limit_pubmed_rps)
SEMANTIC_SCHOLAR_RATE_LIMITER = AsyncRateLimiter(1 / settings.rate_limit_semantic_scholar_rps)
