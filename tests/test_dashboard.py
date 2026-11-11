from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote_plus

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
    enqueue_job,
    finish_job,
    mark_enriched,
)
from mediateca.core.config import Settings, settings
from mediateca.core.config_store import (
    FLARESOLVERR_URL_KEY,
    TMDB_API_TOKEN_KEY,
    effective_tmdb_api_token,
    get_config_value,
    set_config_value,
)
from mediateca.core.db import Base
from mediateca.core.models import AppConfig  # noqa: F401  (registra la tabla)
from mediateca.core.scheduling import load_schedule_settings
from mediateca.dashboard.queries import (
    catalog_coverage,
    enrichment_percentage,
    flaresolverr_config,
    job_status_counts,
    job_type_counts,
    recent_jobs,
    tmdb_config,
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
        inicio = client.get("/")
        tareas = client.get("/tareas")
        health = client.get("/health")
    finally:
        _clear_overrides()

    assert inicio.status_code == 200
    assert tareas.status_code == 200
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "db": "ok"}
    html = inicio.text
    assert 'http-equiv="refresh" content="42"' in html
    assert "pending" in html
    assert "completed" in html
    assert "failed" in html
    assert "50%" in html
    assert "Enriquecimiento" in html
    assert "error visible" not in html
    assert "Trabajos recientes" not in html
    assert "Tareas bajo demanda" in tareas.text
    assert "error visible" in tareas.text
    assert f"<td>{running.id}</td>" in tareas.text


def test_dashboard_sin_tabla_app_config_no_se_degrada(
    monkeypatch, tmp_path
) -> None:
    session = _session()
    AppConfig.__table__.drop(session.get_bind())
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "flaresolverr_url", None)

    client = _client_for(session)
    try:
        response = client.get("/configuracion")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert "Estado degradado" not in response.text
    assert "Configuracion de FlareSolverr" in response.text
    assert "desactivada" in response.text


def test_app_muestra_estado_degradado_sin_trazas(monkeypatch) -> None:
    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("db down"))

        def scalar(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("db down"))

        def scalars(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("db down"))

        def get_bind(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("db down"))

    monkeypatch.setattr(settings, "worker_heartbeat_file", Path("/no/existe"))

    broken = BrokenSession()

    def dependency():
        yield broken

    dashboard_module.app.dependency_overrides[dashboard_module.get_session] = dependency
    client = TestClient(dashboard_module.app)
    try:
        responses = [
            client.get("/"),
            client.get("/tareas"),
            client.get("/configuracion"),
        ]
        health = client.get("/health")
    finally:
        _clear_overrides()

    for response in responses:
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
            for path in ("/", "/tareas", "/configuracion"):
                assert client.get(path).status_code == 200
    finally:
        _clear_overrides()

    assert session.scalar(select(func.count(HarvestJob.id))) == before_jobs
    assert session.scalar(select(func.count(Edicion.id))) == before_ediciones


def test_flaresolverr_config_respeta_la_precedencia(monkeypatch) -> None:
    session = _session()
    monkeypatch.setattr(settings, "flaresolverr_url", None)

    vacia = flaresolverr_config(session)
    assert vacia.source == "ninguno"
    assert vacia.active is False

    monkeypatch.setattr(settings, "flaresolverr_url", "http://env:8191/")
    desde_entorno = flaresolverr_config(session)
    assert desde_entorno.source == "entorno"
    assert desde_entorno.effective_url == "http://env:8191"
    assert desde_entorno.active is True

    set_config_value(session, FLARESOLVERR_URL_KEY, "http://db:8191/")
    session.commit()
    desde_dashboard = flaresolverr_config(session)
    assert desde_dashboard.source == "dashboard"
    assert desde_dashboard.saved_url == "http://db:8191"
    assert desde_dashboard.effective_url == "http://db:8191"
    assert desde_dashboard.active is True

    set_config_value(session, FLARESOLVERR_URL_KEY, "ftp://invalido")
    session.commit()
    invalida = flaresolverr_config(session)
    assert invalida.source == "entorno"
    assert invalida.effective_url == "http://env:8191"


def test_dashboard_muestra_configuracion_y_metricas(monkeypatch, tmp_path) -> None:
    session = _session()
    set_config_value(session, FLARESOLVERR_URL_KEY, "http://db:8191")
    job = create_job(session, "enrich")
    finish_job(
        session,
        job,
        status="completed",
        stats={
            "processed": 3,
            "errors": 0,
            "captchas": 3,
            "captchas_solved": 2,
            "captchas_failed": 1,
            "session_renewals": 1,
        },
    )
    session.commit()

    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    client = _client_for(session)
    try:
        inicio = client.get("/")
        configuracion = client.get("/configuracion")
    finally:
        _clear_overrides()

    assert inicio.status_code == 200
    assert configuracion.status_code == 200
    html = configuracion.text
    assert 'action="/config/flaresolverr"' in html
    assert 'value="http://db:8191"' in html
    assert "activa" in html
    assert "dashboard" in html
    assert "Captchas resueltos" in inicio.text
    assert "Captchas fallidos" in inicio.text
    assert ">2</strong>" in inicio.text
    assert ">1</strong>" in inicio.text


def test_post_guarda_la_url_de_flaresolverr(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    client = _client_for(session)
    try:
        response = client.post(
            "/config/flaresolverr",
            data={"url": " http://flare:8191/ "},
            follow_redirects=False,
        )
        guardada = get_config_value(session, FLARESOLVERR_URL_KEY)
        configuracion = client.get("/configuracion")
    finally:
        _clear_overrides()

    assert response.status_code == 303
    assert response.headers["location"].startswith("/configuracion")
    assert guardada == "http://flare:8191"
    assert 'value="http://flare:8191"' in configuracion.text


def test_post_limpia_la_url_y_usa_el_entorno(monkeypatch, tmp_path) -> None:
    session = _session()
    set_config_value(session, FLARESOLVERR_URL_KEY, "http://db:8191")
    session.commit()
    monkeypatch.setattr(settings, "flaresolverr_url", "http://env:8191")
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")

    client = _client_for(session)
    try:
        response = client.post(
            "/config/flaresolverr",
            data={"url": ""},
            follow_redirects=False,
        )
        guardada = get_config_value(session, FLARESOLVERR_URL_KEY)
        configuracion = client.get("/configuracion")
    finally:
        _clear_overrides()

    assert response.status_code == 303
    assert response.headers["location"].startswith("/configuracion")
    assert guardada is None
    assert "Origen: entorno" in configuracion.text
    assert "http://env:8191" in configuracion.text


def test_post_url_invalida_no_modifica_la_configuracion(monkeypatch, tmp_path) -> None:
    session = _session()
    set_config_value(session, FLARESOLVERR_URL_KEY, "http://db:8191")
    session.commit()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")

    client = _client_for(session)
    try:
        response = client.post(
            "/config/flaresolverr",
            data={"url": "ftp://invalido"},
            follow_redirects=False,
        )
        guardada = get_config_value(session, FLARESOLVERR_URL_KEY)
        error_page = client.get(response.headers["location"])
    finally:
        _clear_overrides()

    assert response.status_code == 303
    assert response.headers["location"].startswith("/configuracion?error=")
    assert guardada == "http://db:8191"
    assert "debe usar http o https" in error_page.text


def test_post_error_de_base_de_datos_muestra_mensaje(
    monkeypatch, tmp_path
) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")

    def fallo(*args, **kwargs):
        raise OperationalError("INSERT", {}, Exception("db down"))

    monkeypatch.setattr(dashboard_module, "set_config_value", fallo)

    client = _client_for(session)
    try:
        response = client.post(
            "/config/flaresolverr",
            data={"url": "http://flare:8191"},
            follow_redirects=False,
        )
        error_page = client.get(response.headers["location"])
    finally:
        _clear_overrides()

    assert response.status_code == 303
    assert response.headers["location"].startswith("/configuracion?error=")
    assert "No se pudo guardar la configuracion de FlareSolverr" in error_page.text


def test_dashboard_muestra_programacion_y_tareas(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", None)

    client = _client_for(session)
    try:
        configuracion = client.get("/configuracion")
        tareas = client.get("/tareas")
    finally:
        _clear_overrides()

    assert configuracion.status_code == 200
    assert tareas.status_code == 200
    assert "Programacion" in configuracion.text
    assert "Tareas bajo demanda" in tareas.text
    assert "Buscar novedades" in tareas.text
    assert "Enriquecer pendientes" in tareas.text


def test_post_programacion_guarda_los_intervalos(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", None)

    client = _client_for(session)
    try:
        response = client.post(
            "/config/schedule",
            data={
                "enabled": "true",
                "discover_interval_hours": "6",
                "full_sweep_interval_hours": "0",
                "enrich_interval_hours": "24",
                "enrich_batch_size": "1000",
                "index_interval_hours": "48",
                "captcha_pause_minutes": "15",
            },
            follow_redirects=False,
        )
        schedule = load_schedule_settings(session)
    finally:
        _clear_overrides()

    assert response.status_code == 303
    assert response.headers["location"].startswith("/configuracion")
    assert schedule.enabled is True
    assert schedule.discover_interval_hours == 6
    assert schedule.full_sweep_interval_hours == 0
    assert schedule.enrich_interval_hours == 24
    assert schedule.enrich_batch_size == 1000
    assert schedule.index_interval_hours == 48
    assert schedule.captcha_pause_minutes == 15


def test_post_job_encola_descubrimiento(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", None)

    client = _client_for(session)
    try:
        response = client.post(
            "/jobs",
            data={"job_type": "discover", "mode": "incremental"},
            follow_redirects=False,
        )
        job = session.scalars(
            select(HarvestJob).where(HarvestJob.job_type == "discover")
        ).first()
    finally:
        _clear_overrides()

    assert response.status_code == 303
    assert response.headers["location"].startswith("/tareas")
    assert job is not None
    assert job.status == "pending"


def test_post_job_duplicado_no_crea_otro(monkeypatch, tmp_path) -> None:
    session = _session()
    enqueue_job(session, "enrich")
    session.commit()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", None)

    client = _client_for(session)
    try:
        response = client.post(
            "/jobs",
            data={"job_type": "enrich", "limit": "100"},
            follow_redirects=False,
        )
        total = len(
            list(session.scalars(select(HarvestJob).where(HarvestJob.job_type == "enrich")))
        )
    finally:
        _clear_overrides()

    assert response.status_code == 303
    assert response.headers["location"].startswith("/tareas?error=")
    assert total == 1
    assert "Ya hay un trabajo" in unquote_plus(response.headers["location"])


def test_escritura_requiere_token_si_esta_configurado(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", "secreto")

    client = _client_for(session)
    try:
        denied = client.post(
            "/jobs",
            data={"job_type": "discover", "mode": "incremental"},
            follow_redirects=False,
        )
        no_job = session.scalars(
            select(HarvestJob).where(HarvestJob.job_type == "discover")
        ).first()
        login = client.post(
            "/admin/login",
            data={"token": "secreto"},
            follow_redirects=False,
        )
        allowed = client.post(
            "/jobs",
            data={"job_type": "discover", "mode": "incremental"},
            follow_redirects=False,
        )
        job = session.scalars(
            select(HarvestJob).where(HarvestJob.job_type == "discover")
        ).first()
    finally:
        _clear_overrides()

    assert denied.status_code == 303
    assert "Token de administracion" in unquote_plus(denied.headers["location"])
    assert no_job is None
    assert login.status_code == 303
    assert allowed.status_code == 303
    assert job is not None
    assert job.status == "pending"


def test_tmdb_config_respeta_la_precedencia(monkeypatch) -> None:
    session = _session()
    monkeypatch.setattr(settings, "tmdb_api_token", None)

    vacia = tmdb_config(session)
    assert vacia.source == "ninguno"
    assert vacia.active is False
    assert vacia.masked_token is None
    assert vacia.saved is False

    monkeypatch.setattr(settings, "tmdb_api_token", "env-token-123456")
    desde_entorno = tmdb_config(session)
    assert desde_entorno.source == "entorno"
    assert desde_entorno.active is True
    assert desde_entorno.saved is False
    assert desde_entorno.masked_token == "****3456"

    set_config_value(session, TMDB_API_TOKEN_KEY, "db-token-123456")
    session.commit()
    desde_dashboard = tmdb_config(session)
    assert desde_dashboard.source == "dashboard"
    assert desde_dashboard.saved is True
    assert desde_dashboard.masked_token == "****3456"

    set_config_value(session, TMDB_API_TOKEN_KEY, "token con espacios")
    session.commit()
    invalida = tmdb_config(session)
    assert invalida.source == "entorno"


def test_dashboard_muestra_configuracion_tmdb(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "tmdb_api_token", "env-token-123456")

    client = _client_for(session)
    try:
        response = client.get("/configuracion")
    finally:
        _clear_overrides()

    html = response.text
    assert response.status_code == 200
    assert "Configuracion de TMDB" in html
    assert 'action="/config/tmdb"' in html
    assert "Origen: entorno" in html
    assert "****3456" in html
    assert "env-token-123456" not in html


def test_post_guarda_token_tmdb(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", None)
    monkeypatch.setattr(settings, "tmdb_api_token", None)

    client = _client_for(session)
    try:
        response = client.post(
            "/config/tmdb",
            data={"token": "db-token-123456"},
            follow_redirects=False,
        )
        dashboard = client.get("/configuracion")
    finally:
        _clear_overrides()

    assert response.status_code == 303
    assert response.headers["location"].startswith("/configuracion")
    assert get_config_value(session, TMDB_API_TOKEN_KEY) == "db-token-123456"
    assert dashboard.status_code == 200
    assert "Origen: dashboard" in dashboard.text
    assert "****3456" in dashboard.text
    assert "db-token-123456" not in dashboard.text


def test_post_token_tmdb_vacio_conserva(monkeypatch, tmp_path) -> None:
    session = _session()
    set_config_value(session, TMDB_API_TOKEN_KEY, "db-token-123456")
    session.commit()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", None)
    monkeypatch.setattr(settings, "tmdb_api_token", None)

    client = _client_for(session)
    try:
        response = client.post(
            "/config/tmdb",
            data={"token": ""},
            follow_redirects=False,
        )
    finally:
        _clear_overrides()

    assert response.status_code == 303
    assert response.headers["location"].startswith("/configuracion")
    assert get_config_value(session, TMDB_API_TOKEN_KEY) == "db-token-123456"
    assert "No se ha modificado" in unquote_plus(response.headers["location"])


def test_post_borra_token_tmdb(monkeypatch, tmp_path) -> None:
    session = _session()
    set_config_value(session, TMDB_API_TOKEN_KEY, "db-token-123456")
    session.commit()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", None)
    monkeypatch.setattr(settings, "tmdb_api_token", "env-token-123456")

    client = _client_for(session)
    try:
        response = client.post(
            "/config/tmdb",
            data={"clear": "true"},
            follow_redirects=False,
        )
        dashboard = client.get("/configuracion")
    finally:
        _clear_overrides()

    assert response.status_code == 303
    assert response.headers["location"].startswith("/configuracion")
    assert get_config_value(session, TMDB_API_TOKEN_KEY) is None
    assert effective_tmdb_api_token(session) == "env-token-123456"
    assert "Origen: entorno" in dashboard.text


def test_post_token_tmdb_invalido_no_modifica(monkeypatch, tmp_path, caplog) -> None:
    session = _session()
    set_config_value(session, TMDB_API_TOKEN_KEY, "db-token-123456")
    session.commit()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", None)

    client = _client_for(session)
    try:
        response = client.post(
            "/config/tmdb",
            data={"token": "token con espacios"},
            follow_redirects=False,
        )
    finally:
        _clear_overrides()

    assert response.status_code == 303
    assert response.headers["location"].startswith("/configuracion?error=")
    assert get_config_value(session, TMDB_API_TOKEN_KEY) == "db-token-123456"
    assert "no puede contener espacios" in unquote_plus(response.headers["location"])
    assert "token con espacios" not in caplog.text


def test_token_tmdb_no_aparece_en_logs(monkeypatch, tmp_path, caplog) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", None)
    token = "db-token-123456"

    client = _client_for(session)
    try:
        client.post("/config/tmdb", data={"token": token}, follow_redirects=False)
    finally:
        _clear_overrides()

    assert token not in caplog.text


def test_post_tmdb_exige_token_de_administracion(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", "secreto")

    client = _client_for(session)
    try:
        denied = client.post(
            "/config/tmdb",
            data={"token": "db-token-123456"},
            follow_redirects=False,
        )
        after_denied = get_config_value(session, TMDB_API_TOKEN_KEY)
        client.post("/admin/login", data={"token": "secreto"}, follow_redirects=False)
        allowed = client.post(
            "/config/tmdb",
            data={"token": "db-token-123456"},
            follow_redirects=False,
        )
    finally:
        _clear_overrides()

    assert denied.status_code == 303
    assert denied.headers["location"].startswith("/configuracion?error=")
    assert "Token de administracion" in unquote_plus(denied.headers["location"])
    assert after_denied is None
    assert allowed.status_code == 303
    assert get_config_value(session, TMDB_API_TOKEN_KEY) == "db-token-123456"


def test_post_tmdb_error_de_base_de_datos(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", None)

    def fallo(*args, **kwargs):  # noqa: ANN002, ANN003
        raise OperationalError("INSERT", {}, Exception("db down"))

    monkeypatch.setattr(dashboard_module, "set_config_value", fallo)

    client = _client_for(session)
    try:
        response = client.post(
            "/config/tmdb",
            data={"token": "db-token-123456"},
            follow_redirects=False,
        )
    finally:
        _clear_overrides()

    assert response.status_code == 303
    assert response.headers["location"].startswith("/configuracion?error=")
    assert "No se pudo guardar la configuracion de TMDB" in unquote_plus(
        response.headers["location"]
    )


def test_navegacion_lateral_y_seccion_activa(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", None)

    client = _client_for(session)
    try:
        inicio = client.get("/")
        tareas = client.get("/tareas")
        configuracion = client.get("/configuracion")
    finally:
        _clear_overrides()

    assert 'href="/tareas"' in inicio.text
    assert 'href="/configuracion"' in inicio.text
    assert '<a href="/" class="nav-link active" aria-current="page">Inicio</a>' in inicio.text
    assert '<a href="/tareas" class="nav-link active" aria-current="page">Tareas</a>' in tareas.text
    assert '<a href="/configuracion" class="nav-link active" aria-current="page">Configuracion</a>' in configuracion.text
    for html in (inicio.text, tareas.text, configuracion.text):
        assert html.count('aria-current="page"') == 1


def test_inicio_no_incluye_tareas_ni_configuracion(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", None)

    client = _client_for(session)
    try:
        response = client.get("/")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert "Tareas bajo demanda" not in response.text
    assert "Trabajos recientes" not in response.text
    assert "Configuracion de FlareSolverr" not in response.text
    assert "Configuracion de TMDB" not in response.text
    assert "Programacion" not in response.text
    assert 'action="/config/' not in response.text


def test_tareas_no_incluye_configuracion(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", None)

    client = _client_for(session)
    try:
        response = client.get("/tareas")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert "Tareas bajo demanda" in response.text
    assert "Trabajos recientes" in response.text
    assert "Configuracion de FlareSolverr" not in response.text
    assert "Configuracion de TMDB" not in response.text
    assert "Programacion" not in response.text


def test_configuracion_no_incluye_tabla_trabajos(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", None)

    client = _client_for(session)
    try:
        response = client.get("/configuracion")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert "Programacion" in response.text
    assert "Configuracion de FlareSolverr" in response.text
    assert "Configuracion de TMDB" in response.text
    assert "Trabajos recientes" not in response.text
    assert "Tareas bajo demanda" not in response.text


def test_refresco_solo_en_inicio_y_tareas(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_refresh_seconds", 42)
    monkeypatch.setattr(settings, "dashboard_admin_token", None)

    client = _client_for(session)
    try:
        inicio = client.get("/")
        tareas = client.get("/tareas")
        configuracion = client.get("/configuracion")
    finally:
        _clear_overrides()

    assert 'http-equiv="refresh" content="42"' in inicio.text
    assert 'http-equiv="refresh" content="42"' in tareas.text
    assert 'http-equiv="refresh"' not in configuracion.text
    assert "Sin refresco automatico" in configuracion.text


def test_login_respeta_next_valido(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", "secreto")

    client = _client_for(session)
    try:
        response = client.post(
            "/admin/login",
            data={"token": "secreto", "next": "/tareas"},
            follow_redirects=False,
        )
    finally:
        _clear_overrides()

    assert response.status_code == 303
    assert response.headers["location"] == "/tareas"


def test_login_next_invalido_cae_en_inicio(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", "secreto")

    client = _client_for(session)
    try:
        response = client.post(
            "/admin/login",
            data={"token": "secreto", "next": "https://evil.example"},
            follow_redirects=False,
        )
    finally:
        _clear_overrides()

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_admin_error_usa_next(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", "secreto")

    client = _client_for(session)
    try:
        tmdb = client.post(
            "/config/tmdb",
            data={"token": "db-token-123456", "next": "/configuracion"},
            follow_redirects=False,
        )
        jobs = client.post(
            "/jobs",
            data={"job_type": "discover", "next": "/tareas"},
            follow_redirects=False,
        )
    finally:
        _clear_overrides()

    assert tmdb.headers["location"].startswith("/configuracion?error=")
    assert "Token de administracion" in unquote_plus(tmdb.headers["location"])
    assert jobs.headers["location"].startswith("/tareas?error=")
    assert "Token de administracion" in unquote_plus(jobs.headers["location"])


def test_configuracion_oculta_formularios_sin_admin(monkeypatch, tmp_path) -> None:
    session = _session()
    monkeypatch.setattr(settings, "worker_heartbeat_file", tmp_path / "missing")
    monkeypatch.setattr(settings, "dashboard_admin_token", "secreto")

    client = _client_for(session)
    try:
        bloqueada = client.get("/configuracion")
        client.post(
            "/admin/login",
            data={"token": "secreto", "next": "/configuracion"},
            follow_redirects=False,
        )
        desbloqueada = client.get("/configuracion")
    finally:
        _clear_overrides()

    assert "Desbloquea la administracion" in bloqueada.text
    assert 'action="/config/tmdb"' not in bloqueada.text
    assert 'action="/config/tmdb"' in desbloqueada.text
