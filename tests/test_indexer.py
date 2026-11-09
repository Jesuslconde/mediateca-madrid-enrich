from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mediateca.catalog.indexer import build_document
from mediateca.catalog.parser import parse_file
from mediateca.catalog.repository import upsert_edicion
from mediateca.core.db import Base


def _session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_build_document_incluye_bibliotecas_sin_disponibilidad(dvd_fixture) -> None:
    session = _session()
    edicion = upsert_edicion(session, parse_file(str(dvd_fixture)))
    session.commit()

    document = build_document(edicion)

    assert document["ejemplares"] == 2
    assert len(document["bibliotecas"]) == 2
    assert "disponible" not in document
    assert "estado" not in document
