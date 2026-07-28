from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
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
    quality_report: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: {
            "overall": {
                "title": 0.0,
                "year": 0.0,
                "doi": 0.0,
                "abstract": 0.0,
                "duplicate_rate": 0.0,
            },
            "sources": {},
        },
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CollectionStatus.RUNNING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    @property
    def public_id(self) -> str:
        return f"COL-{self.id:04d}"


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
