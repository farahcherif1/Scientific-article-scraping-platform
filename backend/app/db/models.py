from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.entities import CollectionStatus


class Base(DeclarativeBase):
    pass


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    sources: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    article_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CollectionStatus.RUNNING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    @property
    def public_id(self) -> str:
        return f"COL-{self.id:04d}"

    @staticmethod
    def numeric_id(public_id: str) -> int:
        return int(public_id.removeprefix("COL-"))


class Article(Base):
    """
    Normalized, deduplicated article persisted for a collection run
    (US-04.1/US-04.2 wiring + US-05.1 territory, see docs/limitations.md).
    One row per `ArticleClean` (app/domain/entities.py) produced by
    `app/use_cases/start_collection.py` after normalize -> deduplicate.
    Indexed on every column the results API (US-04.3/US-05.1/US-05.2)
    sorts or filters by.
    """

    __tablename__ = "articles"
    __table_args__ = (
        Index("ix_articles_collection_run_id", "collection_run_id"),
        Index("ix_articles_year", "year"),
        Index("ix_articles_source", "source"),
        Index("ix_articles_doi", "doi"),
        Index("ix_articles_is_duplicate", "is_duplicate"),
        Index("ix_articles_relevance_score", "relevance_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_run_id: Mapped[int] = mapped_column(
        ForeignKey("collection_runs.id"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    authors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    venue: Mapped[str | None] = mapped_column(String(500), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    categories: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    keywords_auto: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    source: Mapped[str] = mapped_column(String(100), nullable=False)
    search_keyword: Mapped[str] = mapped_column(String(200), nullable=False)
    collection_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    duplicate_group_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    duplicate_similarity_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicate_rule: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    missing_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    relevance_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CustomConnector(Base):
    """
    A researcher-configured connector to a scientific source outside the
    5 built-in ones (EP-custom-connectors). `config` is the full, validated
    `CustomConnectorConfig` (app/connectors/generic_config.py), stored as
    JSON rather than normalized columns since it's read/written as one unit
    (the wizard, the test-connection endpoint, and GenericConnector all
    consume the whole object) and its shape may grow without a migration.
    """

    __tablename__ = "custom_connectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
