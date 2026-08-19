from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from backend.config import DB_PATH, ensure_data_dir
from backend.db import AppSetting, Category, Candidate, Email, Job  # noqa: F401
from backend.schemas import DEFAULT_CATEGORIES

engine = None


def get_engine():
    global engine
    if engine is None:
        ensure_data_dir()
        engine = create_engine(
            f"sqlite:///{DB_PATH}",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return engine


def _add_missing_columns() -> None:
    """`create_all` never alters an existing table, so new nullable columns are
    added here to keep databases from earlier versions usable."""
    added = {"candidates": {"marked_at": "DATETIME"}}
    with get_engine().begin() as conn:
        for table, columns in added.items():
            present = {
                row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            if not present:
                continue
            for name, sql_type in columns.items():
                if name not in present:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"
                    )


def _backfill_marked_at() -> None:
    """Items marked before the app recorded a mark date have no timestamp. The
    extraction date is the closest bound available, since an item cannot be
    marked before it exists. Idempotent: every later mark sets its own date."""
    with get_engine().begin() as conn:
        conn.exec_driver_sql(
            "UPDATE candidates SET marked_at = created_at "
            "WHERE marked_at IS NULL AND (important = 1 OR shortlisted = 1)"
        )


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())
    _add_missing_columns()
    _backfill_marked_at()
    with session_scope() as session:
        existing = {c.name for c in session.exec(select(Category)).all()}
        for i, name in enumerate(DEFAULT_CATEGORIES):
            if name not in existing:
                session.add(Category(name=name, is_default=True, sort_order=i))
        session.commit()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = Session(get_engine())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
