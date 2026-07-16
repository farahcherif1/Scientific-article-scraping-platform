"""Shared connector contract (US-03.2/03.3/03.5 all implement this)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from app.domain.entities import RawArticle


@dataclass
class SearchFilters:
    year_from: Optional[int] = None
    year_to: Optional[int] = None


class BaseConnector(ABC):
    name: str

    @abstractmethod
    async def search(
        self,
        keyword: str,
        max_results: int,
        filters: dict | None = None,
    ) -> list[RawArticle]:
        """Return up to max_results RawArticle records for the given keyword."""
        raise NotImplementedError

    