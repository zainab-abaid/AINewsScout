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


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())
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
