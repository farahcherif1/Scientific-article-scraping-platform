from abc import ABC, abstractmethod

from app.domain.entities import RawArticle


class BaseConnector(ABC):
    """
    Common interface every scientific-source connector must implement.
    Adding a new source means writing one file that implements this.
    """

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
