from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.models import Base

connect_args = {"check_same_thread": False} if settings.db_url.startswith("sqlite") else {}
engine = create_engine(settings.db_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def ensure_schema(engine_to_use=None) -> None:
    target_engine = engine_to_use or engine
    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())

    if "collection_runs" not in existing_tables:
        Base.metadata.create_all(bind=target_engine)
        return

    collection_columns = {column["name"] for column in inspector.get_columns("collection_runs")}
    if "quality_report" not in collection_columns:
        with target_engine.begin() as conn:
            conn.execute(text("ALTER TABLE collection_runs ADD COLUMN quality_report JSON"))

    if "created_at" not in collection_columns:
        with target_engine.begin() as conn:
            conn.execute(text("ALTER TABLE collection_runs ADD COLUMN created_at DATETIME"))

    if "stats" not in collection_columns:
        with target_engine.begin() as conn:
            conn.execute(text("ALTER TABLE collection_runs ADD COLUMN stats JSON"))

    Base.metadata.create_all(bind=target_engine)


def init_db() -> None:
    ensure_schema(engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
