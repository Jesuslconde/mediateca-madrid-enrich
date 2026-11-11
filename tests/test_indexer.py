from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mediateca.catalog.indexer import (
    FACET_FIELDS,
    FILTERABLE_ATTRIBUTES,
    MeiliIndexer,
    build_document,
    build_filters,
)
from mediateca.catalog.jobs import create_stub
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


class _FakeIndex:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}
        self.batches: list[list[str]] = []

    def add_documents(self, documents, primary_key="id"):
        self.batches.append([document["id"] for document in documents])
        for document in documents:
            self.documents[document["id"]] = document

    def delete_all_documents(self):
        self.documents.clear()


def _fake_indexer() -> tuple[MeiliIndexer, _FakeIndex]:
    index = _FakeIndex()
    indexer = MeiliIndexer.__new__(MeiliIndexer)
    indexer.client = object()
    indexer.index = index
    indexer.ensure_index = lambda: None  # type: ignore[method-assign]
    return indexer, index


def test_detail_complete_distingue_stub_de_ficha_enriquecida(dvd_fixture) -> None:
    session = _session()
    stub = create_stub(session, "123")
    session.commit()

    stub_document = build_document(stub)

    assert stub_document["detail_complete"] is False
    assert stub_document["is_stub"] is True

    edicion = upsert_edicion(session, parse_file(str(dvd_fixture)))
    session.commit()

    complete = build_document(edicion)

    assert complete["detail_complete"] is True
    assert complete["is_stub"] is False


def test_index_titns_solo_actualiza_los_titn_indicados(dvd_fixture) -> None:
    session = _session()
    create_stub(session, "1")
    create_stub(session, "2")
    upsert_edicion(session, parse_file(str(dvd_fixture)))
    session.commit()
    indexer, index = _fake_indexer()

    first = indexer.index_titns(session, ["1"])
    second = indexer.index_titns(session, ["2", "2101557"])
    missing = indexer.index_titns(session, ["no-existe"])

    assert first == 1
    assert second == 2
    assert missing == 0
    assert index.batches == [["1"], ["2", "2101557"]]
    assert set(index.documents) == {"1", "2", "2101557"}


def test_index_titns_envia_lotes_de_200() -> None:
    session = _session()
    for number in range(201):
        create_stub(session, f"{number:04d}")
    session.commit()
    indexer, index = _fake_indexer()

    total = indexer.index_titns(session, [f"{number:04d}" for number in range(201)])

    assert total == 201
    assert [len(batch) for batch in index.batches] == [200, 1]


def test_detail_complete_es_un_atributo_filtrable() -> None:
    assert "detail_complete" in FILTERABLE_ATTRIBUTES
    assert "is_stub" in FILTERABLE_ATTRIBUTES


def test_build_document_incluye_paises_origen(dvd_fixture) -> None:
    session = _session()
    edicion = upsert_edicion(session, parse_file(str(dvd_fixture)))
    edicion.paises_origen = ["ES", "FR"]
    session.commit()

    document = build_document(edicion)

    assert document["paises_origen"] == ["ES", "FR"]


def test_build_document_incluye_lista_vacia_para_sin_tmdb() -> None:
    session = _session()
    stub = create_stub(session, "sin-tmdb")
    session.commit()

    assert build_document(stub)["paises_origen"] == []


def test_faceta_y_filtro_de_paises_origen() -> None:
    assert "paises_origen" in FACET_FIELDS
    assert "paises_origen" in FILTERABLE_ATTRIBUTES

    filters = build_filters(paises_origen=["ES", "FR"])
    assert filters is not None
    assert 'paises_origen = "ES"' in filters
    assert 'paises_origen = "FR"' in filters
    assert " OR " in filters


def test_index_reset_reconstruye_paises_origen(dvd_fixture) -> None:
    session = _session()
    edicion = upsert_edicion(session, parse_file(str(dvd_fixture)))
    edicion.paises_origen = ["ES"]
    session.commit()
    indexer, index = _fake_indexer()
    index.documents["antiguo"] = {"id": "antiguo"}

    total = indexer.index_editions(session, reset=True)

    assert total == 1
    assert "antiguo" not in index.documents
    assert index.documents[edicion.titn]["paises_origen"] == ["ES"]
