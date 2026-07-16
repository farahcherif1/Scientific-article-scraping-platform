"""
In-memory, per-process cache for raw connector responses, keyed by
(source, keyword, params). Entries expire after settings.cache_ttl_hours.

MVP-scoped: single-process SQLite backend, so an in-memory cache is enough;
logged as a limitation for the multi-worker/Postgres cutover.
"""
from __future__ import annotations

import time
from typing import Optional

from app.config import settings

CacheKey = tuple[str, str, tuple[tuple[str, object], ...]]

_store: dict[CacheKey, tuple[float, list[dict]]] = {}


def _make_key(source: str, keyword: str, params: dict) -> CacheKey:
    return (source, keyword.lower(), tuple(sorted(params.items())))


def get_cached(source: str, keyword: str, params: dict) -> Optional[list[dict]]:
    key = _make_key(source, keyword, params)
    entry = _store.get(key)
    if entry is None:
        return None
    expires_at, records = entry
    if time.monotonic() >= expires_at:
        del _store[key]
        return None
    return records


def set_cached(source: str, keyword: str, params: dict, records: list[dict]) -> None:
    key = _make_key(source, keyword, params)
    ttl_s = settings.cache_ttl_hours * 3600
    _store[key] = (time.monotonic() + ttl_s, records)


def clear_cache() -> None:
    """Test helper — drops all entries."""
    _store.clear()
