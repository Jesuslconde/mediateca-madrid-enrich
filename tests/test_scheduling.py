from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from mediateca_shared.models import HarvestJob
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mediateca.catalog.jobs import (
    JobAlreadyActive,
    claim_job,
    create_job,
    create_stub,
    enqueue_discover_job,
    enqueue_job,
    finish_job,
)
from mediateca.catalog.repository import count_pending_titns, select_pending_titns
from mediateca.catalog.scheduler import enqueue_due_jobs, run_scheduler
from mediateca.core.config import Settings
from mediateca.core.db import Base
from mediateca.core.scheduling import (
    ScheduleSettings,
    ScheduleValidationError,
    build_schedule_status,
    load_schedule_settings,
    save_schedule_settings,
    validate_schedule_settings,
)


def _session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _completed_discover(
    session,
    *,
    created_at: datetime,
    cursor_doc: int = 100,
    cursor_titn: str = "100",
    mode: str = "full",
) -> HarvestJob:
    job = create_job(
        session,
        "discover",
        cursor_doc=cursor_doc,
        cursor_titn=cursor_titn,
    )
    job.created_at = created_at
    claim_job(session, now=created_at)
    finish_job(
        session,
        job,
        status="completed",
        now=created_at + timedelta(minutes=5),
        stats={"mode": mode, "processed": 10},
    )
    session.commit()
    return job


def test_settings_de_programacion_por_defecto_y_entorno(monkeypatch) -> None:
    monkeypatch.delenv("MEDIATECA_SCHEDULER_ENABLED", raising=False)
    monkeypatch.delenv("MEDIATECA_SCHEDULER_POLL_SECONDS", raising=False)
    defaults = Settings(_env_file=None)
    assert defaults.scheduler_enabled is True
    assert defaults.scheduler_poll_seconds == 60.0

    monkeypatch.setenv("MEDIATECA_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("MEDIATECA_SCHEDULER_POLL_SECONDS", "15")
    configured = Settings(_env_file=None)
    assert configured.scheduler_enabled is False
    assert configured.scheduler_poll_seconds == 15.0


def test_configuracion_de_programacion_ida_y_vuelta() -> None:
    session = _session()
    original = ScheduleSettings(
        enabled=False,
        discover_interval_hours=6,
        full_sweep_interval_hours=0,
        enrich_interval_hours=24,
        enrich_batch_size=1000,
    )

    save_schedule_settings(session, original)
    session.commit()

    assert load_schedule_settings(session) == original


def test_validacion_de_intervalos_y_lote() -> None:
    with pytest.raises(ScheduleValidationError):
        validate_schedule_settings(
            ScheduleSettings(True, 0, 168, 12, 5000)
        )
    with pytest.raises(ScheduleValidationError):
        validate_schedule_settings(
            ScheduleSettings(True, 12, -1, 12, 5000)
        )
    with pytest.raises(ScheduleValidationError):
        validate_schedule_settings(
            ScheduleSettings(True, 12, 168, 12, 0)
        )


def test_encolado_deduplica_por_tipo() -> None:
    session = _session()
    enqueue_job(session, "enrich")
    session.commit()

    with pytest.raises(JobAlreadyActive):
        enqueue_job(session, "enrich")


def test_descubrimiento_incremental_usa_el_cursor_anterior() -> None:
    session = _session()
    previous = _completed_discover(
        session,
        created_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        cursor_doc=1234,
        cursor_titn="9999",
    )

    job = enqueue_discover_job(session, mode="incremental")
    session.commit()

    assert job.cursor_doc == previous.cursor_doc
    assert job.cursor_titn == previous.cursor_titn
    assert job.stats["mode"] == "incremental"


def test_sin_descubrimiento_previo_el_incremental_es_completo() -> None:
    session = _session()
    job = enqueue_discover_job(session, mode="incremental")
    session.commit()

    assert job.stats["mode"] == "full"
    assert job.cursor_doc is None
    assert job.cursor_titn is None


def test_enriquecimiento_solo_selecciona_los_nuevos() -> None:
    session = _session()
    old = create_stub(session, "1", seen_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC))
    new = create_stub(session, "2", seen_at=datetime(2026, 1, 1, 11, 0, tzinfo=UTC))
    session.commit()

    since = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    assert select_pending_titns(session, since=since) == [new.titn]
    assert count_pending_titns(session, since=since) == 1
    assert select_pending_titns(session) == [old.titn, new.titn]


def test_estado_de_programacion_calcula_proxima_ejecucion() -> None:
    session = _session()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    _completed_discover(
        session,
        created_at=now - timedelta(hours=13),
        mode="full",
    )

    status = build_schedule_status(
        session,
        ScheduleSettings(True, 12, 168, 12, 5000),
        now=now,
    )

    assert status.discover.last_run is not None
    assert status.discover.next_run == now - timedelta(hours=1)
    assert status.discover.active is False


def test_scheduler_encola_descubrimiento_incremental() -> None:
    session = _session()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    previous = _completed_discover(
        session,
        created_at=now - timedelta(hours=13),
        cursor_doc=50,
        cursor_titn="500",
        mode="full",
    )

    jobs = enqueue_due_jobs(
        session,
        now=now,
        settings=ScheduleSettings(True, 12, 168, 12, 5000),
    )
    session.commit()

    assert len(jobs) == 1
    assert jobs[0].job_type == "discover"
    assert jobs[0].stats["mode"] == "incremental"
    assert jobs[0].cursor_doc == previous.cursor_doc
    assert jobs[0].cursor_titn == previous.cursor_titn


def test_scheduler_no_encola_si_esta_desactivado() -> None:
    session = _session()
    jobs = enqueue_due_jobs(
        session,
        now=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        settings=ScheduleSettings(False, 12, 168, 12, 5000),
    )

    assert jobs == []
    assert session.scalars(select(HarvestJob)).first() is None


def test_scheduler_encola_enriquecimiento_de_nuevos() -> None:
    session = _session()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    completed = _completed_discover(
        session,
        created_at=now - timedelta(hours=1),
        mode="incremental",
    )
    create_stub(session, "1", seen_at=now - timedelta(minutes=30))
    session.commit()

    jobs = enqueue_due_jobs(
        session,
        now=now,
        settings=ScheduleSettings(True, 12, 168, 12, 100),
    )
    session.commit()

    assert len(jobs) == 1
    assert jobs[0].job_type == "enrich"
    assert jobs[0].batch_size == 100
    assert jobs[0].stats["since"] == (
        completed.started_at or completed.created_at
    ).isoformat()


def test_scheduler_respeta_trabajos_activos() -> None:
    session = _session()
    enqueue_job(session, "discover")
    session.commit()

    jobs = enqueue_due_jobs(
        session,
        now=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        settings=ScheduleSettings(True, 12, 168, 12, 5000),
    )

    assert jobs == []


def test_run_scheduler_una_iteracion() -> None:
    session = _session()

    def factory():
        return session

    iterations = run_scheduler(factory, poll_seconds=1, max_iterations=1)

    assert iterations == 1


def test_scheduler_encola_reconciliacion_del_indice() -> None:
    session = _session()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    _completed_discover(
        session,
        created_at=now - timedelta(hours=1),
        mode="incremental",
    )

    jobs = enqueue_due_jobs(
        session,
        now=now,
        settings=ScheduleSettings(
            True,
            12,
            0,
            12,
            5000,
            index_interval_hours=168,
        ),
    )
    session.commit()

    assert [job.job_type for job in jobs] == ["index"]
    assert jobs[0].status == "pending"
