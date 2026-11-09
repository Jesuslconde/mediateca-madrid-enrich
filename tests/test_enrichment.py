from __future__ import annotations

from datetime import UTC, datetime

from mediateca_shared.models import Edicion, Ejemplar
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mediateca.catalog.harvester import Harvester
from mediateca.catalog.jobs import create_stub
from mediateca.catalog.repository import select_pending_titns
from mediateca.core.config import settings
from mediateca.core.db import Base

DVD_TITN = "2101557"
BLURAY_TITN = "2107423"


def _session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class _FakeEnrichmentClient:
    delay = 0.0
    max_retries = 3

    def __init__(self, pages: dict[str, str], *, failing: set[str] | None = None) -> None:
        self.pages = pages
        self.failing = failing or set()
        self.calls: list[str] = []
        self.failures: dict[str, int] = {}

    def fetch_by_titn(self, titn: str) -> tuple[str, str]:
        self.calls.append(titn)
        if titn in self.failing:
            self.failures[titn] = self.failures.get(titn, 0) + 1
            raise RuntimeError("ficha no disponible")
        return self.pages[titn], f"https://opac.example/TITN={titn}"


def test_enriquecimiento_es_idempotente_y_sin_snapshots(
    monkeypatch, tmp_path, dvd_fixture
) -> None:
    monkeypatch.setattr(settings, "raw_dir", tmp_path)
    session = _session()
    create_stub(session, DVD_TITN)
    session.commit()
    client = _FakeEnrichmentClient(
        {DVD_TITN: dvd_fixture.read_text(encoding="utf-8")}
    )
    harvester = Harvester(session, client=client)

    stats = harvester.harvest_enrichment(limit=10, delay=0)

    assert stats["processed"] == 1
    assert stats["errors"] == 0
    assert stats["failed"] == []
    edicion = session.scalars(select(Edicion).where(Edicion.titn == DVD_TITN)).one()
    assert edicion.is_stub is False
    assert edicion.detail_fetched_at is not None
    assert session.scalar(select(func.count(Ejemplar.id))) == 2
    assert "snapshots" not in Base.metadata.tables
    assert list(tmp_path.iterdir()) == []

    edicion.detail_fetched_at = None
    session.commit()
    harvester.harvest_enrichment(limit=10, delay=0)

    assert session.scalar(select(func.count(Edicion.id))) == 1
    assert session.scalar(select(func.count(Ejemplar.id))) == 2
    assert "snapshots" not in Base.metadata.tables


def test_seleccion_pendiente_no_repite_enriquecidas_y_respeta_cursor() -> None:
    session = _session()
    for titn in ("1", "2", "3"):
        create_stub(session, titn)
    enriquecida = session.scalars(select(Edicion).where(Edicion.titn == "2")).one()
    enriquecida.detail_fetched_at = datetime.now(UTC)
    session.commit()

    pendientes = select_pending_titns(session, limit=10)

    assert pendientes == ["1", "3"]
    assert select_pending_titns(session, limit=10, after_titn="1") == ["3"]
    assert select_pending_titns(session, limit=1) == ["1"]


def test_un_fallo_no_bloquea_el_resto_del_lote(
    dvd_fixture, bluray_fixture
) -> None:
    session = _session()
    for titn in (DVD_TITN, BLURAY_TITN):
        create_stub(session, titn)
    session.commit()
    client = _FakeEnrichmentClient(
        {
            DVD_TITN: dvd_fixture.read_text(encoding="utf-8"),
            BLURAY_TITN: bluray_fixture.read_text(encoding="utf-8"),
        },
        failing={DVD_TITN},
    )

    stats = Harvester(session, client=client).harvest_enrichment(limit=10, delay=0)

    assert client.failures[DVD_TITN] == 3
    assert client.calls.count(DVD_TITN) == 3
    assert client.calls.count(BLURAY_TITN) == 1
    assert stats["processed"] == 1
    assert stats["errors"] == 1
    assert stats["failed"] == [DVD_TITN]
    fallida = session.scalars(select(Edicion).where(Edicion.titn == DVD_TITN)).one()
    correcta = session.scalars(select(Edicion).where(Edicion.titn == BLURAY_TITN)).one()
    assert fallida.detail_fetched_at is None
    assert correcta.detail_fetched_at is not None
