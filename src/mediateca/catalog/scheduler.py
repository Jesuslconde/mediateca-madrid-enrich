from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from mediateca.catalog.jobs import (
    JobAlreadyActive,
    enqueue_discover_job,
    enqueue_enrich_job,
    enqueue_index_job,
)
from mediateca.catalog.repository import count_pending_titns
from mediateca.core.logging import get_logger
from mediateca.core.scheduling import (
    ScheduleSettings,
    has_active_job,
    last_completed_discover,
    last_full_discover,
    last_job,
    load_schedule_settings,
)

logger = get_logger(__name__)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _is_due(last_run, interval_hours: int, now: datetime) -> bool:
    if interval_hours <= 0:
        return False
    if last_run is None or last_run.created_at is None:
        return True
    created = _as_aware(last_run.created_at)
    if created is None:
        return True
    return now >= created + timedelta(hours=interval_hours)


def enqueue_due_jobs(
    session: Session,
    *,
    now: datetime | None = None,
    settings: ScheduleSettings | None = None,
) -> list:
    current = now or datetime.now(UTC)
    schedule = settings or load_schedule_settings(session)
    if not schedule.enabled:
        return []

    enqueued = []

    if not has_active_job(session, "discover") and _is_due(
        last_job(session, "discover"), schedule.discover_interval_hours, current
    ):
        full_due = schedule.full_sweep_interval_hours > 0 and _is_due(
            last_full_discover(session), schedule.full_sweep_interval_hours, current
        )
        mode = "full" if full_due else "incremental"
        try:
            job = enqueue_discover_job(session, mode=mode, reason="scheduler")
        except JobAlreadyActive:
            logger.info("Ya hay un descubrimiento activo; no se encola otro")
        else:
            enqueued.append(job)
            logger.info(
                "Descubrimiento encolado por el scheduler",
                extra={"job_id": job.id, "job_type": job.job_type, "action": mode},
            )

    last_discover = last_completed_discover(session)
    if (
        last_discover is not None
        and not has_active_job(session, "discover")
        and not has_active_job(session, "enrich")
    ):
        since = last_discover.started_at or last_discover.created_at
        pending = count_pending_titns(session, since=since)
        if pending > 0 and _is_due(
            last_job(session, "enrich"), schedule.enrich_interval_hours, current
        ):
            try:
                job = enqueue_enrich_job(
                    session,
                    since=since,
                    batch_size=schedule.enrich_batch_size,
                    reason="scheduler",
                )
            except JobAlreadyActive:
                logger.info("Ya hay un enriquecimiento activo; no se encola otro")
            else:
                enqueued.append(job)
                logger.info(
                    "Enriquecimiento encolado por el scheduler",
                    extra={
                        "job_id": job.id,
                        "job_type": job.job_type,
                        "pending": pending,
                    },
                )

    if (
        not has_active_job(session, "discover")
        and not has_active_job(session, "enrich")
        and not has_active_job(session, "index")
        and _is_due(
            last_job(session, "index"), schedule.index_interval_hours, current
        )
    ):
        try:
            job = enqueue_index_job(session)
        except JobAlreadyActive:
            logger.info("Ya hay una indexacion activa; no se encola otra")
        else:
            enqueued.append(job)
            logger.info(
                "Indexacion de reconciliacion encolada por el scheduler",
                extra={"job_id": job.id, "job_type": job.job_type},
            )

    if enqueued:
        session.flush()
    return enqueued


def run_scheduler(
    session_factory: sessionmaker[Session],
    *,
    poll_seconds: float = 60.0,
    max_iterations: int | None = None,
    stop_event: threading.Event | None = None,
) -> int:
    iterations = 0
    while stop_event is None or not stop_event.is_set():
        with session_factory() as session:
            try:
                enqueued = enqueue_due_jobs(session)
                session.commit()
            except Exception:  # noqa: BLE001
                session.rollback()
                logger.exception("Fallo al calcular los trabajos programados")
                enqueued = []
        iterations += 1
        if enqueued:
            logger.info("Trabajos programados encolados: %s", len(enqueued))
        if max_iterations is not None and iterations >= max_iterations:
            break
        wait = max(1.0, poll_seconds)
        if stop_event is not None:
            stop_event.wait(wait)
        else:
            time.sleep(wait)
    return iterations
