from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from mediateca_shared.models import HarvestJob
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from typer.testing import CliRunner

import mediateca.dashboard.app as dashboard_module
from mediateca.api.routers.ingest import get_session as api_get_session
from mediateca.catalog.jobs import (
    claim_job,
    coverage,
    create_job,
    create_stub,
    finish_job,
    ingest_metrics,
    mark_enriched,
    recent_jobs,
    worker_state,
)
from mediateca.cli import app as cli_app
from mediateca.core.db import Base
from mediateca.core.logging import JsonFormatter


def _session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _seeded_session():
    session = _session()
    start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    stub = create_stub(session, "1")
    enriched = create_stub(session, "2")
    mark_enriched(session, enriched)
    job = create_job(session, "enrich")
    claim_job(session, now=start)
    finish_job(
        session,
        job,
        status="completed",
        now=start + timedelta(seconds=2),
        stats={
            "processed": 1,
            "errors": 0,
            "captchas": 1,
            "captchas_solved": 1,
            "captchas_failed": 0,
            "session_renewals": 2,
            "failed": ["9"],
        },
    )
    session.commit()
    return session, stub, enriched


def test_consultas_de_trabajos_cobertura_y_metricas() -> None:
    session, _, _ = _seeded_session()

    cover = coverage(session)
    metrics = ingest_metrics(session, cover)
    jobs = recent_jobs(session, limit=10)

    assert cover.ediciones == 2
    assert cover.enriquecidas == 1
    assert cover.pendientes == 1
    assert metrics.processed == 1
    assert metrics.errors == 0
    assert metrics.captchas == 1
    assert metrics.captchas_solved == 1
    assert metrics.captchas_failed == 0
    assert metrics.session_renewals == 2
    assert metrics.failed == 1
    assert metrics.pending == 1
    assert metrics.average_ms == 2000.0
    assert len(jobs) == 1
    assert session.scalar(select(func.count(HarvestJob.id))) == 1


def test_worker_state_ok_y_degraded(tmp_path) -> None:
    session = _session()
    path = tmp_path / "heartbeat"
    path.write_text("now", encoding="utf-8")
    now = datetime.now(UTC)
    stamp = now.timestamp()
    os.utime(path, (stamp, stamp))

    ok = worker_state(
        session, now=now, heartbeat_file=path, stale_seconds=120
    )
    assert ok.status == "ok"
    assert ok.source == "file"

    old = stamp - 600
    os.utime(path, (old, old))
    degraded = worker_state(
        session, now=now, heartbeat_file=path, stale_seconds=120
    )
    assert degraded.status == "degraded"

    empty = worker_state(
        session,
        now=now,
        heartbeat_file=tmp_path / "missing",
        stale_seconds=120,
    )
    assert empty.status == "degraded"
    assert empty.last_heartbeat is None


def test_api_status_y_coverage() -> None:
    session, _, _ = _seeded_session()

    def dependency():
        yield session

    dashboard_module.app.dependency_overrides[api_get_session] = dependency
    client = TestClient(dashboard_module.app)
    try:
        status_response = client.get("/api/ingest/status")
        coverage_response = client.get("/api/ingest/coverage")
        docs = client.get("/docs")
        openapi = client.get("/openapi.json")
    finally:
        dashboard_module.app.dependency_overrides.clear()

    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["coverage"]["ediciones"] == 2
    assert payload["coverage"]["enriquecidas"] == 1
    assert payload["coverage"]["porcentaje"] == 50
    assert payload["coverage"]["fallidas"] == 1
    assert payload["coverage"]["desaparecidas"] == 0
    assert payload["metrics"]["captchas"] == 1
    assert payload["metrics"]["captchas_solved"] == 1
    assert payload["metrics"]["captchas_failed"] == 0
    assert payload["metrics"]["session_renewals"] == 2
    assert payload["metrics"]["average_ms"] == 2000.0
    assert payload["worker"]["status"] == "degraded"
    assert len(payload["jobs"]) == 1

    assert coverage_response.status_code == 200
    coverage_payload = coverage_response.json()
    assert coverage_payload["coverage"]["pendientes"] == 1
    assert "jobs" not in coverage_payload

    assert docs.status_code == 200
    assert openapi.status_code == 200
    schemas = openapi.json()["components"]["schemas"]
    assert "IngestStatusOut" in schemas
    assert "IngestCoverageOut" in schemas


def test_cli_ingest_status(monkeypatch) -> None:
    session, _, _ = _seeded_session()

    from contextlib import contextmanager

    @contextmanager
    def fake_session_scope():
        yield session
        session.commit()

    import mediateca.cli as cli_module

    monkeypatch.setattr(cli_module, "session_scope", fake_session_scope)

    result = CliRunner().invoke(cli_app, ["ingest-status"])

    assert result.exit_code == 0, result.output
    assert "Trabajos de ingesta" in result.output
    assert "Cobertura y metricas" in result.output
    assert "enrich" in result.output
    assert "1" in result.output


def test_logs_json_incluyen_campos_estructurados() -> None:
    record = logging.LogRecord(
        name="mediateca.catalog.harvester",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Ficha procesada",
        args=(),
        exc_info=None,
    )
    record.job_id = 7
    record.job_type = "enrich"
    record.titn = "2101557"
    record.doc = 12
    record.result = "enriched"
    record.duration_ms = 12.5

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["job_id"] == 7
    assert payload["job_type"] == "enrich"
    assert payload["titn"] == "2101557"
    assert payload["doc"] == 12
    assert payload["result"] == "enriched"
    assert payload["duration_ms"] == 12.5
