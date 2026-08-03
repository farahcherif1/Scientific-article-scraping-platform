import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.db.models import Base
from app.db.session import ensure_schema


def test_ensure_schema_adds_missing_collection_run_columns():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        engine = create_engine(f"sqlite:///{db_path}")

        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE collection_runs"))
            conn.execute(
                text(
                    "CREATE TABLE collection_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, keywords JSON NOT NULL, sources JSON NOT NULL, article_count INTEGER NOT NULL DEFAULT 0, duplicate_count INTEGER NOT NULL DEFAULT 0, status VARCHAR(20) NOT NULL, created_at DATETIME)"
                )
            )

        ensure_schema(engine)

        inspector = inspect(engine)
        columns = {column["name"] for column in inspector.get_columns("collection_runs")}
        assert "quality_report" in columns
        assert "created_at" in columns
