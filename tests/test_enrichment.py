from __future__ import annotations

from datetime import UTC, datetime

import pytest
from mediateca_shared.models import Edicion, Ejemplar
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mediateca.catalog.harvester import CaptchaRequired, Harvester
from mediateca.catalog.jobs import build_tmdb_client, create_stub
from mediateca.catalog.repository import select_pending_titns
from mediateca.catalog.tmdb import (
    TmdbError,
    TmdbMovieDetail,
    TmdbSearchResult,
)
from mediateca.core.config import settings
from mediateca.core.config_store import TMDB_API_TOKEN_KEY, set_config_value
from mediateca.core.db import Base
from mediateca.core.models import AppConfig  # noqa: F401  (registra la tabla)

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


class _FakeTmdbClient:
    def __init__(
        self,
        *,
        results: list[TmdbSearchResult] | None = None,
        detail: TmdbMovieDetail | None = None,
        error: Exception | None = None,
    ) -> None:
        self.results = results or []
        self.detail = detail
        self.error = error
        self.search_calls: list[tuple[str, int | None]] = []
        self.detail_calls: list[int] = []

    def search_movie(self, query: str, *, year: int | None = None):
        self.search_calls.append((query, year))
        if self.error is not None:
            raise self.error
        return self.results

    def get_movie(self, movie_id: int):
        self.detail_calls.append(movie_id)
        if self.error is not None:
            raise self.error
        assert self.detail is not None
        return self.detail


def _tmdb_result(movie_id: int = 10) -> TmdbSearchResult:
    return TmdbSearchResult(
        id=movie_id,
        title="20.000 especies de abejas",
        original_title="20.000 especies de abejas",
        release_date="2023-01-01",
        popularity=1.0,
    )


def _tmdb_detail(countries: tuple[str, ...] = ("ES", "FR")) -> TmdbMovieDetail:
    return TmdbMovieDetail(
        id=10,
        title="20.000 especies de abejas",
        original_title="20.000 especies de abejas",
        release_date="2023-01-01",
        production_countries=list(countries),
    )


def test_enriquecimiento_tmdb_empareja_y_guarda_paises(dvd_fixture) -> None:
    session = _session()
    create_stub(session, DVD_TITN)
    session.commit()
    opac = _FakeEnrichmentClient({DVD_TITN: dvd_fixture.read_text(encoding="utf-8")})
    tmdb = _FakeTmdbClient(results=[_tmdb_result()], detail=_tmdb_detail())

    stats = Harvester(session, client=opac, tmdb_client=tmdb).harvest_enrichment(
        limit=10, delay=0
    )

    edicion = session.scalars(select(Edicion).where(Edicion.titn == DVD_TITN)).one()
    assert edicion.paises_origen == ["ES", "FR"]
    assert edicion.tmdb_id == 10
    assert edicion.tmdb_enriched_at is not None
    assert edicion.pais is not None
    assert stats["tmdb_matched"] == 1
    assert stats["tmdb_unmatched"] == 0
    assert stats["tmdb_errors"] == 0
    assert stats["tmdb_skipped"] == 0


def test_enriquecimiento_tmdb_sin_coincidencia(dvd_fixture) -> None:
    session = _session()
    create_stub(session, DVD_TITN)
    session.commit()
    opac = _FakeEnrichmentClient({DVD_TITN: dvd_fixture.read_text(encoding="utf-8")})
    tmdb = _FakeTmdbClient(results=[])

    stats = Harvester(session, client=opac, tmdb_client=tmdb).harvest_enrichment(
        limit=10, delay=0
    )

    edicion = session.scalars(select(Edicion).where(Edicion.titn == DVD_TITN)).one()
    assert edicion.paises_origen == []
    assert edicion.tmdb_id is None
    assert edicion.tmdb_enriched_at is None
    assert stats["tmdb_unmatched"] == 1
    assert stats["tmdb_errors"] == 0


def test_enriquecimiento_sin_token_omite_tmdb(dvd_fixture) -> None:
    session = _session()
    create_stub(session, DVD_TITN)
    session.commit()
    opac = _FakeEnrichmentClient({DVD_TITN: dvd_fixture.read_text(encoding="utf-8")})

    stats = Harvester(session, client=opac).harvest_enrichment(limit=10, delay=0)

    edicion = session.scalars(select(Edicion).where(Edicion.titn == DVD_TITN)).one()
    assert edicion.tmdb_enriched_at is None
    assert stats["tmdb_skipped"] == 1


def test_error_tmdb_no_invalida_ficha_opac(dvd_fixture) -> None:
    session = _session()
    create_stub(session, DVD_TITN)
    session.commit()
    opac = _FakeEnrichmentClient({DVD_TITN: dvd_fixture.read_text(encoding="utf-8")})
    tmdb = _FakeTmdbClient(error=TmdbError("TMDB no disponible"))

    stats = Harvester(session, client=opac, tmdb_client=tmdb).harvest_enrichment(
        limit=10, delay=0
    )

    edicion = session.scalars(select(Edicion).where(Edicion.titn == DVD_TITN)).one()
    assert edicion.detail_fetched_at is not None
    assert edicion.tmdb_enriched_at is None
    assert stats["tmdb_errors"] == 1
    assert stats["errors"] == 0


def test_fallo_tmdb_conserva_paises_previos(dvd_fixture) -> None:
    session = _session()
    create_stub(session, DVD_TITN)
    session.commit()
    edicion = session.scalars(select(Edicion).where(Edicion.titn == DVD_TITN)).one()
    anterior = datetime(2025, 1, 1, tzinfo=UTC)
    edicion.paises_origen = ["ES"]
    edicion.tmdb_id = 99
    edicion.tmdb_enriched_at = anterior
    edicion.detail_fetched_at = None
    session.commit()

    opac = _FakeEnrichmentClient({DVD_TITN: dvd_fixture.read_text(encoding="utf-8")})
    tmdb = _FakeTmdbClient(error=TmdbError("TMDB no disponible"))

    Harvester(session, client=opac, tmdb_client=tmdb).harvest_enrichment(
        limit=10, delay=0
    )

    edicion = session.scalars(select(Edicion).where(Edicion.titn == DVD_TITN)).one()
    assert edicion.paises_origen == ["ES"]
    assert edicion.tmdb_id == 99
    assert edicion.tmdb_enriched_at == anterior
    assert edicion.detail_fetched_at is not None


def test_captcha_del_opac_no_llama_a_tmdb() -> None:
    session = _session()
    create_stub(session, DVD_TITN)
    session.commit()

    class _CaptchaClient:
        delay = 0.0
        max_retries = 3

        def fetch_by_titn(self, titn: str):
            raise CaptchaRequired("captcha")

    tmdb = _FakeTmdbClient(results=[_tmdb_result()], detail=_tmdb_detail())

    with pytest.raises(CaptchaRequired):
        Harvester(session, client=_CaptchaClient(), tmdb_client=tmdb).harvest_enrichment(
            limit=10, delay=0
        )

    assert tmdb.search_calls == []
    assert tmdb.detail_calls == []


def test_build_tmdb_client_usa_el_token_efectivo(monkeypatch) -> None:
    session = _session()
    monkeypatch.setattr(settings, "tmdb_api_token", None)
    set_config_value(session, TMDB_API_TOKEN_KEY, "db-token-123456")
    session.commit()

    primero = build_tmdb_client(session)
    assert primero is not None
    assert primero.token == "db-token-123456"
    primero.close()

    set_config_value(session, TMDB_API_TOKEN_KEY, "db-token-654321")
    session.commit()
    segundo = build_tmdb_client(session)
    assert segundo is not None
    assert segundo.token == "db-token-654321"
    segundo.close()

    set_config_value(session, TMDB_API_TOKEN_KEY, None)
    monkeypatch.setattr(settings, "tmdb_api_token", "env-token-123456")
    session.commit()
    tercero = build_tmdb_client(session)
    assert tercero is not None
    assert tercero.token == "env-token-123456"
    tercero.close()
