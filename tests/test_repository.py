from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from mediateca_shared.models import (
    Biblioteca,
    Edicion,
    Ejemplar,
    Materia,
    Obra,
)
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mediateca.catalog.parser import parse_file, parse_search_results
from mediateca.catalog.repository import mark_absent_since, upsert_edicion, upsert_stub
from mediateca.core.db import Base


def _session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_upsert_es_idempotente_y_agrupa_obras(dvd_fixture, bluray_fixture) -> None:
    session = _session()
    dvd = parse_file(str(dvd_fixture))
    bluray = parse_file(str(bluray_fixture))

    upsert_edicion(session, dvd)
    upsert_edicion(session, dvd)
    session.commit()

    assert session.scalar(select(func.count(Edicion.id))) == 1
    assert session.scalar(select(func.count(Ejemplar.id))) == 2
    assert session.scalar(select(func.count(Biblioteca.id))) == 2
    assert session.scalar(select(func.count(Materia.id))) == 2

    edicion = session.scalars(select(Edicion)).one()
    bibliotecas = sorted({ejemplar.biblioteca.nombre for ejemplar in edicion.ejemplares})
    assert len(bibliotecas) == 2
    assert edicion.is_stub is False
    assert edicion.discovery_seen_at is not None
    assert edicion.detail_fetched_at is not None

    tables = Base.metadata.tables
    assert "historial_disponibilidad" not in tables
    assert "disponible" not in tables["ediciones"].columns
    assert "disponible" not in tables["ejemplares"].columns
    assert "estado" not in tables["ejemplares"].columns

    upsert_edicion(session, bluray)
    session.commit()

    assert session.scalar(select(func.count(Edicion.id))) == 2
    assert session.scalar(select(func.count(Obra.id))) == 1
    assert session.scalar(select(func.count(Ejemplar.id))) == 3

    ediciones = session.scalars(select(Edicion)).all()
    soportes = sorted(soporte for edicion in ediciones for soporte in edicion.soportes)
    assert soportes == ["Blu-ray", "DVD"]


def test_reupsert_tras_commit_no_rompe_relaciones(dvd_fixture) -> None:
    session = _session()
    dvd = parse_file(str(dvd_fixture))

    upsert_edicion(session, dvd)
    session.commit()
    upsert_edicion(session, dvd)
    session.commit()

    assert session.scalar(select(func.count(Edicion.id))) == 1
    assert session.scalar(select(func.count(Ejemplar.id))) == 2
    assert session.scalar(select(func.count(Materia.id))) == 2


def test_deduplica_ejemplares_identicos(dvd_fixture) -> None:
    session = _session()
    dvd = parse_file(str(dvd_fixture))
    dvd.ejemplares.append(replace(dvd.ejemplares[0]))

    upsert_edicion(session, dvd)
    session.commit()

    assert session.scalar(select(func.count(Ejemplar.id))) == 2


def test_upsert_stub_crea_edicion_con_metadatos(search_results_fixture) -> None:
    session = _session()
    parsed = parse_search_results(
        search_results_fixture.read_text(encoding="utf-8")
    )[0]

    first = upsert_stub(session, parsed)
    second = upsert_stub(session, parsed)
    session.commit()

    assert first.id == second.id
    assert session.scalar(select(func.count(Edicion.id))) == 1
    assert first.is_stub is True
    assert first.discovery_seen_at is not None
    assert first.detail_fetched_at is None
    assert first.titulo.startswith("20.000 especies de abejas")
    assert first.anio == 2023
    assert first.idioma == "spa"
    assert first.soportes == ["DVD"]
    assert first.soporte_principal == "DVD"
    assert first.marc["T300a"].startswith("1 DVD-Video")


def test_upsert_stub_no_sobrescribe_edicion_enriquecida(dvd_fixture) -> None:
    session = _session()
    dvd = parse_file(str(dvd_fixture))
    upsert_edicion(session, dvd)
    session.commit()

    stub = replace(
        dvd,
        titulo="Titulo del listado que no debe pisar",
        anio=1900,
        soportes=["VHS"],
    )
    upsert_stub(session, stub)
    session.commit()

    edicion = session.scalars(select(Edicion)).one()
    assert edicion.is_stub is False
    assert edicion.detail_fetched_at is not None
    assert edicion.titulo.startswith("20.000 especies de abejas")
    assert edicion.anio == 2023
    assert edicion.soportes == ["DVD"]


def test_mark_absent_since_marca_sin_borrar(search_results_fixture) -> None:
    session = _session()
    parsed = parse_search_results(
        search_results_fixture.read_text(encoding="utf-8")
    )
    for item in parsed:
        upsert_stub(session, item)

    antiguo = datetime.now(UTC) - timedelta(days=1)
    for edicion in session.scalars(select(Edicion)):
        edicion.discovery_seen_at = antiguo
    session.commit()

    ausentes = mark_absent_since(session, {"2101557"}, since=datetime.now(UTC))
    session.commit()

    assert ausentes == 2
    assert session.scalar(select(func.count(Edicion.id))) == 3
    ediciones = {edicion.titn: edicion for edicion in session.scalars(select(Edicion))}
    assert ediciones["2101557"].missing_at is None
    assert ediciones["2107423"].missing_at is not None
    assert ediciones["2109999"].missing_at is not None




