from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from mediateca_shared.db import Base
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from mediateca.core.config import settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
    return _session_factory


def init_db() -> None:
    """Crea el esquema si no existe. Es idempotente."""
    from mediateca_shared import models  # noqa: F401  (registra las tablas)

    Base.metadata.create_all(bind=get_engine())


def get_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
