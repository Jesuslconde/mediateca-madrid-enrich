from __future__ import annotations

from contextlib import contextmanager

from mediateca_shared.models import Edicion
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from typer.testing import CliRunner

import mediateca.cli as cli_module
from mediateca.catalog.harvester import Harvester, SearchPage
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
        lambda session, client: Harvester(
            session, client=client, raw_dir=tmp_path
        ),
    )

    result = CliRunner().invoke(
        cli_module.app, ["discover", "--max-pages", "1", "--delay", "0.1"]
    )

    assert result.exit_code == 0, result.output
    assert session.scalar(select(func.count(Edicion.id))) == 3
