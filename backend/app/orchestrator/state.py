"""
In-memory progress store for running collections (US-03.4 T-03.4.4).

Single-process MVP store, same tradeoff as app/infra/cache.py: fine for the
SQLite/single-worker deployment, not shared across workers or persisted
across restarts - revisit once the platform moves to multiple backend
processes (see docs/limitations.md).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.domain.entities import CollectionStatus


@dataclass
class SourceProgress:
    source: str
    status: str = "pending"  # pending | running | done | failed
    detail: str | None = None
    articles_fetched: int = 0


@dataclass
class CollectionState:
    id: str
    keywords: list[str]
    sources: list[str]
    status: str = CollectionStatus.RUNNING
    current_keyword: str | None = None
    warning: str | None = None
    error: str | None = None
    abort_requested: bool = False
    completed_pairs: int = 0
    started_monotonic: float = field(default_factory=time.monotonic)
    finished_monotonic: float | None = None
    source_progress: dict[str, SourceProgress] = field(init=False)

    def __post_init__(self) -> None:
        self.source_progress = {source: SourceProgress(source=source) for source in self.sources}

    @property
    def total_pairs(self) -> int:
        return len(self.sources) * len(self.keywords)

    @property
    def elapsed_seconds(self) -> int:
        end = self.finished_monotonic if self.finished_monotonic is not None else time.monotonic()
        return max(0, int(end - self.started_monotonic))

    def mark_finished(self) -> None:
        """Freezes elapsed_seconds once the run reaches a terminal status."""
        if self.finished_monotonic is None:
            self.finished_monotonic = time.monotonic()

    @property
    def overall_progress(self) -> float:
        if self.total_pairs == 0:
            return 100.0
        return min(100.0, 100.0 * self.completed_pairs / self.total_pairs)


_STORE: dict[str, CollectionState] = {}


def create_state(id: str, *, keywords: list[str], sources: list[str]) -> CollectionState:
    state = CollectionState(id=id, keywords=keywords, sources=sources)
    _STORE[id] = state
    return state


def get_state(id: str) -> CollectionState | None:
    return _STORE.get(id)


def clear_all() -> None:
    """Test-only helper to reset the store between test modules."""
    _STORE.clear()
