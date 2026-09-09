from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _connect_args(database_url: str) -> dict[str, bool]:
    return {"check_same_thread": False} if database_url.startswith("sqlite") else {}


settings = get_settings()
engine = create_engine(settings.database_url, connect_args=_connect_args(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    # V1 开发便利措施。生产改用 Alembic 迁移并由发布流程显式执行。
    from app import models  # noqa: F401

    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    migrate_log_type(engine)


def migrate_log_type(bind) -> None:
    """Additive upgrade; existing jobs remain client queries."""
    with bind.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(400004)"))
        elif connection.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        columns = {c["name"] for c in inspect(connection).get_columns("query_job_contexts")}
        if "log_type" not in columns:
            connection.execute(text(
                "ALTER TABLE query_job_contexts ADD COLUMN log_type VARCHAR(16) NOT NULL DEFAULT 'client'"
            ))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
