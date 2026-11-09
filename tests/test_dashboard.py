from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from mediateca_shared.models import Edicion, HarvestJob
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import mediateca.dashboard.app as dashboard_module
from mediateca.catalog.jobs import (
    claim_job,
    create_job,
    create_stub,
    finish_job,
    mark_enriched,
)
from mediateca.core.config import Settings, settings
from mediateca.core.db import Base
from mediateca.dashboard.queries import (
    catalog_coverage,
    enrichment_percentage,
    job_status_counts,
    job_type_counts,
    recent_jobs,
    worker_health,
)

ROOT = Path(__file__).resolve().parents[1]


def _session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _override_session(session):
    def dependency():
        yield session

    return dependency


def _client_for(session) -> TestClient:
    dashboard_module.app.dependency_overrides[dashboard_module.get_session] = (
        _override_session(session)
    )
    return TestClient(dashboard_module.app)


def _clear_overrides() -> None:
    dashboard_module.app.dependency_overrides.clear()


def test_settings_dashboard_defaults_y_variables_de_entorno(monkeypatch) -> None:
    names = [
        "MEDIATECA_DASHBOARD_HOST",
        "MEDIATECA_DASHBOARD_PORT",
        "MEDIATECA_DASHBOARD_REFRESH_SECONDS",
        "MEDIATECA_DASHBOARD_RECENT_LIMIT",
        "MEDIATECA_DASHBOARD_WORKER_STALE_SECONDS",
    ]
    for name in names:
        monkeypatch.delenv(name, raising=False)

    defaults = Settings(_env_file=None)
    assert defaults.dashboard_host == "127.0.0.1"
    assert defaults.dashboard_port == 8080
    assert defaults.dashboard_refresh_seconds == 15
    assert defaults.dashboard_recent_limit == 20
    assert defaults.dashboard_worker_stale_seconds == 120

    monkeypatch.setenv("MEDIATECA_DASHBOARD_HOST", "0.0.0.0")
    monkeypatch.setenv("MEDIATECA_DASHBOARD_PORT", "9191")
    monkeypatch.setenv("MEDIATECA_DASHBOARD_REFRESH_SECONDS", "5")
    monkeypatch.setenv("MEDIATECA_DASHBOARD_RECENT_LIMIT", "7")
    monkeypatch.setenv("MEDIATECA_DASHBOARD_WORKER_STALE_SECONDS", "60")

    configured = Settings(_env_file=None)
    assert configured.dashboard_host == "0.0.0.0"
    assert configured.dashboard_port == 9191
    assert configured.dashboard_refresh_seconds == 5
    assert configured.dashboard_recent_limit == 7
    assert configured.dashboard_worker_stale_seconds == 60


def test_env_example_documenta_las_variables_del_dashboard() -> None:
    content = (ROOT / ".env.example").read_text(encoding="utf-8")
    documented = {
        line.split("=", 1)[0]
        for line in content.splitlines()
        if line.startswith("MEDIATECA_DASHBOARD_")
    }
    expected = {
        name.upper()
        for name in Settings.model_fields
        if name.startswith("dashboard_")
    }
    assert documented == {f"MEDIATECA_{name}" for name in expected}


def test_conteos_por_estado_y_tipo() -> None:
    session = _session()
    create_job(session, "discover")
    create_job(session, "enrich")
    failed = create_job(session, "index")
    finish_job(session, failed, status="failed", error="fallo")
    session.commit()

    assert job_status_counts(session) == {
        "pending": 2,
        "running": 0,
        "completed": 0,
        "failed": 1,
        "cancelled": 0,
    }
    assert job_type_counts(session) == {
        "discover": 1,
        "enrich": 1,
        "index": 1,
    }


def test_trabajos_recientes_respeta_orden_y_limite() -> None:
    session = _session()
    jobs = [create_job(session, "discover") for _ in range(3)]
    session.commit()

    recientes = recent_jobs(session, limit=2)

    assert [job.id for job in recientes] == [jobs[2].id, jobs[1].id]
    assert len(recent_jobs(session, limit=10)) == 3


def test_worker_health_ok_y_degraded_con_fichero(tmp_path) -> None:
    session = _session()
    path = tmp_path / "worker.heartbeat"
    path.write_text("now", encoding="utf-8")
    now = datetime.now(UTC)
    stamp = now.timestamp()
    os.utime(path, (stamp, stamp))

    ok = worker_health(session, now=now, heartbeat_file=path, stale_seconds=120)
    assert ok.status == "ok"
    assert ok.source == "file"
    assert ok.last_heartbeat is not None

    old = stamp - 600
    os.utime(path, (old, old))
    degraded = worker_health(
        session, now=now, heartbeat_file=path, stale_seconds=120
    )
    assert degraded.status == "degraded"


def test_worker_health_usa_la_base_de_datos_como_respaldo(tmp_path) -> None:
    session = _session()
    now = datetime.now(UTC)
    create_job(session, "enrich")
    claim_job(session, now=now)
    session.commit()

    healthy = worker_health(
        session,
        now=now,
        heartbeat_file=tmp_path / "missing.heartbeat",
        stale_seconds=120,
    )
    assert healthy.status == "ok"
    assert healthy.source == "database"

    stale = worker_health(
        session,
        now=now + timedelta(minutes=10),
        heartbeat_file=tmp_path / "missing.heartbeat",
        stale_seconds=120,
    )
    assert stale.status == "degraded"

    empty = worker_health(
        _session(),
        now=now,
        heartbeat_file=tmp_path / "missing.heartbeat",
        stale_seconds=120,
    )
    assert empty.status == "degraded"
    assert empty.last_heartbeat is None


def test_cobertura_vacia_y_porcentaje_sin_division_por_cero() -> None:
    session = _session()

    cover = catalog_coverage(session)

    assert cover.ediciones == 0
    assert cover.descubiertas == 0
    assert cover.enriquecidas == 0
    assert cover.pendientes == 0
    assert cover.fallidas == 0
    assert enrichment_percentage(cover) == 0

    create_stub(session, "1")
    enriched = create_stub(session, "2")
    mark_enriched(session, enriched)
    session.commit()

    cover = catalog_coverage(session)
    assert cover.ediciones == 2
    assert cover.enriquecidas == 1
    assert enrichment_percentage(cover) == 50


def test_app_responde_y_muestra_los_datos(monkeypatch, tmp_path) -> None:
    session = _session()
    running = create_job(session, "enrich")
    claim_job(session)
    failed = create_job(session, "index")
    finish_job(session, failed, status="failed", error="error visible")
    create_stub(session, "1")
    enriched = create_stub(session, "2")
    mark_enriched(session, enriched)
    session.commit()

    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_refresh_seconds", 42)

    client = _client_for(session)
    try:
        response = client.get("/")
        health = client.get("/health")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "db": "ok"}
    html = response.text
    assert 'http-equiv="refresh" content="42"' in html
    assert "pending" in html
    assert "completed" in html
    assert "failed" in html
    assert "error visible" in html
    assert "50%" in html
    assert str(running.id) in html
    assert "Enriquecimiento" in html


def test_app_muestra_estado_degradado_sin_trazas(monkeypatch) -> None:
    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("db down"))

        def scalar(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("db down"))

        def scalars(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("db down"))

    monkeypatch.setattr(settings, "worker_heartbeat_file", Path("/no/existe"))

    broken = BrokenSession()

    def dependency():
        yield broken

    dashboard_module.app.dependency_overrides[dashboard_module.get_session] = dependency
    client = TestClient(dashboard_module.app)
    try:
        response = client.get("/")
        health = client.get("/health")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert "Estado degradado" in response.text
    assert "Traceback" not in response.text
    assert "db down" not in response.text
    assert health.status_code == 200
    assert health.json() == {"status": "degraded", "db": "error"}


def test_vista_es_de_solo_lectura(monkeypatch, tmp_path) -> None:
    session = _session()
    create_job(session, "discover")
    create_stub(session, "1")
    session.commit()

    before_jobs = session.scalar(select(func.count(HarvestJob.id)))
    before_ediciones = session.scalar(select(func.count(Edicion.id)))

    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    client = _client_for(session)
    try:
        for _ in range(3):
            assert client.get("/").status_code == 200
    finally:
        _clear_overrides()

    assert session.scalar(select(func.count(HarvestJob.id))) == before_jobs
    assert session.scalar(select(func.count(Edicion.id))) == before_ediciones
