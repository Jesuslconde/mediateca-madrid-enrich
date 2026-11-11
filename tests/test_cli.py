from __future__ import annotations

from contextlib import contextmanager

from mediateca_shared.models import Edicion
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from typer.testing import CliRunner

import mediateca.cli as cli_module
from mediateca.catalog.harvester import Harvester, SearchPage
from mediateca.catalog.jobs import create_stub, mark_enriched
from mediateca.catalog.tmdb import TmdbMovieDetail, TmdbSearchResult
from mediateca.core.db import Base


def _session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_cli_discover_crea_stubs(
    monkeypatch, tmp_path, search_results_fixture
) -> None:
    session = _session()
    html = search_results_fixture.read_text(encoding="utf-8")

    class FakeOpacClient:
        def __init__(self, *args, **kwargs) -> None:
            self.delay = 0.0

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

        def search_all(
            self,
            query: str,
            *,
            max_pages: int | None = None,
            start_doc: int | None = None,
        ):
            yield SearchPage(query=query, total=3, items=[], html=html)

    @contextmanager
    def fake_session_scope():
        yield session
        session.commit()

    monkeypatch.setattr(cli_module, "OpacClient", FakeOpacClient)
    monkeypatch.setattr(cli_module, "session_scope", fake_session_scope)
    monkeypatch.setattr(
        cli_module,
        "Harvester",
        lambda session, client: Harvester(session, client=client),
    )

    result = CliRunner().invoke(
        cli_module.app, ["discover", "--max-pages", "1", "--delay", "0.1"]
    )

    assert result.exit_code == 0, result.output
    assert session.scalar(select(func.count(Edicion.id))) == 3


def test_cli_enrich_procesa_el_lote(monkeypatch, dvd_fixture) -> None:
    session = _session()
    create_stub(session, "2101557")
    session.commit()
    html = dvd_fixture.read_text(encoding="utf-8")

    class FakeOpacClient:
        def __init__(self, *args, **kwargs) -> None:
            self.delay = 0.0

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

        def fetch_by_titn(self, titn: str) -> tuple[str, str]:
            return html, f"https://opac.example/TITN={titn}"

    @contextmanager
    def fake_session_scope():
        yield session
        session.commit()

    monkeypatch.setattr(cli_module, "OpacClient", FakeOpacClient)
    monkeypatch.setattr(cli_module, "session_scope", fake_session_scope)

    result = CliRunner().invoke(
        cli_module.app, ["enrich", "--limit", "5000", "--delay", "0.1"]
    )

    assert result.exit_code == 0, result.output
    edicion = session.scalars(select(Edicion)).one()
    assert edicion.titn == "2101557"
    assert edicion.detail_fetched_at is not None
    assert edicion.is_stub is False


def test_cli_incluye_el_comando_dashboard() -> None:
    result = CliRunner().invoke(cli_module.app, ["--help"])

    assert result.exit_code == 0
    assert "dashboard" in result.output


def test_cli_discover_usa_la_url_de_flaresolverr(monkeypatch) -> None:
    from mediateca.core.config_store import FLARESOLVERR_URL_KEY, set_config_value

    session = _session()
    set_config_value(session, FLARESOLVERR_URL_KEY, "http://db:8191")
    session.commit()

    capturado: dict = {}

    class FakeOpacClient:
        def __init__(self, *args, **kwargs) -> None:
            capturado.update(kwargs)
            self.delay = 0.0

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

        def search_all(
            self,
            query: str,
            *,
            max_pages: int | None = None,
            start_doc: int | None = None,
        ):
            yield SearchPage(query=query, total=0, items=[], html="<html></html>")

    @contextmanager
    def fake_session_scope():
        yield session
        session.commit()

    monkeypatch.setattr(cli_module, "OpacClient", FakeOpacClient)
    monkeypatch.setattr(cli_module, "session_scope", fake_session_scope)

    result = CliRunner().invoke(
        cli_module.app, ["discover", "--max-pages", "1", "--delay", "0.1"]
    )

    assert result.exit_code == 0, result.output
    assert capturado["flaresolverr_url"] == "http://db:8191"


class _FakeTmdbClient:
    def __init__(self, *, match: bool = True) -> None:
        self.match = match
        self.calls: list[tuple[str, int | None]] = []

    def search_movie(self, query: str, *, year: int | None = None):
        self.calls.append((query, year))
        if not self.match:
            return []
        return [
            TmdbSearchResult(
                id=abs(hash(query)) % 100000,
                title=query,
                original_title=query,
                release_date=f"{year or 2020}-01-01",
                popularity=1.0,
            )
        ]

    def get_movie(self, movie_id: int):
        return TmdbMovieDetail(
            id=movie_id,
            title="Pelicula",
            original_title="Pelicula",
            release_date="2020-01-01",
            production_countries=["ES"],
        )

    def close(self) -> None:
        pass


def _enriched_edition(session, titn: str, titulo: str, anio: int):
    edicion = create_stub(session, titn)
    edicion.titulo = titulo
    edicion.anio = anio
    mark_enriched(session, edicion)
    return edicion


def test_cli_tmdb_enrich_procesa_por_lotes_y_reanuda(
    monkeypatch, tmp_path
) -> None:
    session = _session()
    _enriched_edition(session, "1", "Pelicula A", 2020)
    _enriched_edition(session, "2", "Pelicula B", 2021)
    session.commit()

    class FakeOpacClient:
        delay = 0.0

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

    @contextmanager
    def fake_session_scope():
        yield session
        session.commit()

    tmdb = _FakeTmdbClient()
    monkeypatch.setattr(cli_module, "OpacClient", FakeOpacClient)
    monkeypatch.setattr(cli_module, "session_scope", fake_session_scope)
    monkeypatch.setattr(cli_module, "build_tmdb_client", lambda *args, **kwargs: tmdb)

    first = CliRunner().invoke(
        cli_module.app,
        ["tmdb-enrich", "--limit", "1", "--delay", "0", "--no-index"],
    )
    assert first.exit_code == 0, first.output
    ediciones = {
        edicion.titn: edicion for edicion in session.scalars(select(Edicion))
    }
    assert ediciones["1"].tmdb_enriched_at is not None
    assert ediciones["2"].tmdb_enriched_at is None

    second = CliRunner().invoke(
        cli_module.app,
        ["tmdb-enrich", "--limit", "10", "--delay", "0", "--no-index"],
    )
    assert second.exit_code == 0, second.output
    session.expire_all()
    ediciones = {
        edicion.titn: edicion for edicion in session.scalars(select(Edicion))
    }
    assert ediciones["1"].tmdb_enriched_at is not None
    assert ediciones["2"].tmdb_enriched_at is not None


def test_cli_tmdb_enrich_sin_token_falla_sin_modificar(monkeypatch, tmp_path) -> None:
    session = _session()
    edicion = _enriched_edition(session, "1", "Pelicula A", 2020)
    session.commit()

    @contextmanager
    def fake_session_scope():
        yield session
        session.commit()

    monkeypatch.setattr(cli_module, "session_scope", fake_session_scope)
    monkeypatch.setattr(cli_module, "build_tmdb_client", lambda *args, **kwargs: None)

    result = CliRunner().invoke(cli_module.app, ["tmdb-enrich", "--limit", "10"])

    assert result.exit_code == 1
    assert "No hay token de TMDB" in result.output
    session.refresh(edicion)
    assert edicion.tmdb_enriched_at is None


def test_cli_tmdb_enrich_indexa_los_titn_procesados(monkeypatch, tmp_path) -> None:
    session = _session()
    _enriched_edition(session, "1", "Pelicula A", 2020)
    session.commit()

    class FakeOpacClient:
        delay = 0.0

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

    class FakeIndexer:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def index_titns(self, session, titns):  # noqa: ANN001
            self.calls.append(list(titns))
            return len(titns)

    @contextmanager
    def fake_session_scope():
        yield session
        session.commit()

    indexer = FakeIndexer()
    tmdb = _FakeTmdbClient()
    monkeypatch.setattr(cli_module, "OpacClient", FakeOpacClient)
    monkeypatch.setattr(cli_module, "session_scope", fake_session_scope)
    monkeypatch.setattr(cli_module, "build_tmdb_client", lambda *args, **kwargs: tmdb)
    monkeypatch.setattr(cli_module, "MeiliIndexer", lambda: indexer)

    result = CliRunner().invoke(
        cli_module.app,
        ["tmdb-enrich", "--limit", "10", "--delay", "0"],
    )

    assert result.exit_code == 0, result.output
    assert indexer.calls == [["1"]]
