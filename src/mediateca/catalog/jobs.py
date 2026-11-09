from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mediateca_shared.constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_ATTEMPTS,
    FINAL_STATUSES,
    JOB_TYPES,
)
from mediateca_shared.models import Edicion, HarvestJob
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker


@dataclass(slots=True)
class IngestCoverage:
    ediciones: int
    descubiertas: int
    enriquecidas: int
    pendientes: int
    fallidas: int
    trabajos_pendientes: int
    trabajos_en_ejecucion: int
    trabajos_completados: int
    trabajos_fallidos: int


def _now() -> datetime:
    return datetime.now(UTC)


def create_job(
    session: Session,
    job_type: str,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    cursor_doc: int | None = None,
    cursor_titn: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    stats: dict | None = None,
) -> HarvestJob:
    if job_type not in JOB_TYPES:
        raise ValueError(f"Tipo de trabajo no valido: {job_type}")

    job = HarvestJob(
        job_type=job_type,
        status="pending",
        batch_size=batch_size,
        cursor_doc=cursor_doc,
        cursor_titn=cursor_titn,
        max_attempts=max_attempts,
        stats=stats or {},
    )
    session.add(job)
    session.flush()
    return job


def claim_job(
    session: Session,
    *,
    job_types: tuple[str, ...] | list[str] | None = None,
    now: datetime | None = None,
) -> HarvestJob | None:
    stmt = select(HarvestJob).where(HarvestJob.status == "pending")
    if job_types:
        stmt = stmt.where(HarvestJob.job_type.in_(list(job_types)))
    stmt = stmt.order_by(HarvestJob.created_at, HarvestJob.id).limit(1)

    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    job = session.scalars(stmt).first()
    if job is None:
        return None

    timestamp = now or _now()
    job.status = "running"
    job.started_at = timestamp
    job.heartbeat_at = timestamp
    job.attempts = (job.attempts or 0) + 1
    session.flush()
    return job


def touch_job(session: Session, job: HarvestJob, *, now: datetime | None = None) -> None:
    job.heartbeat_at = now or _now()
    session.flush()


def update_cursor(
    session: Session,
    job: HarvestJob,
    *,
    cursor_doc: int | None = None,
    cursor_titn: str | None = None,
    stats: dict | None = None,
) -> None:
    if cursor_doc is not None:
        job.cursor_doc = cursor_doc
    if cursor_titn is not None:
        job.cursor_titn = cursor_titn
    if stats is not None:
        job.stats = stats
    session.flush()


def finish_job(
    session: Session,
    job: HarvestJob,
    *,
    status: str = "completed",
    stats: dict | None = None,
    error: str | None = None,
    now: datetime | None = None,
) -> None:
    if status not in FINAL_STATUSES:
        raise ValueError(f"Estado final no valido: {status}")

    timestamp = now or _now()
    job.status = status
    job.finished_at = timestamp
    job.heartbeat_at = timestamp
    if stats is not None:
        job.stats = stats
    if error is not None:
        job.error = error
    session.flush()


def requeue_job(
    session: Session,
    job: HarvestJob,
    *,
    error: str | None = None,
    now: datetime | None = None,
) -> None:
    job.status = "pending"
    job.started_at = None
    job.heartbeat_at = now or _now()
    if error is not None:
        job.error = error
    session.flush()


def create_stub(
    session: Session,
    titn: str,
    *,
    seen_at: datetime | None = None,
) -> Edicion:
    timestamp = seen_at or _now()
    edicion = session.scalars(select(Edicion).where(Edicion.titn == titn)).first()
    if edicion is None:
        edicion = Edicion(
            titn=titn,
            titulo=titn,
            is_stub=True,
            discovery_seen_at=timestamp,
        )
        session.add(edicion)
        session.flush()
    elif edicion.discovery_seen_at is None:
        edicion.discovery_seen_at = timestamp
        session.flush()
    return edicion


def mark_enriched(
    session: Session,
    edicion: Edicion,
    *,
    fetched_at: datetime | None = None,
) -> None:
    edicion.detail_fetched_at = fetched_at or _now()
    edicion.is_stub = False
    edicion.missing_at = None
    session.flush()


def mark_missing(
    session: Session,
    edicion: Edicion,
    *,
    missing_at: datetime | None = None,
) -> None:
    edicion.missing_at = missing_at or _now()
    session.flush()


def coverage(session: Session) -> IngestCoverage:
    ediciones = session.scalar(select(func.count(Edicion.id))) or 0
    descubiertas = (
        session.scalar(
            select(func.count(Edicion.id)).where(Edicion.discovery_seen_at.is_not(None))
        )
        or 0
    )
    enriquecidas = (
        session.scalar(
            select(func.count(Edicion.id)).where(Edicion.detail_fetched_at.is_not(None))
        )
        or 0
    )
    pendientes = (
        session.scalar(
            select(func.count(Edicion.id)).where(
                or_(Edicion.is_stub.is_(True), Edicion.detail_fetched_at.is_(None))
            )
        )
        or 0
    )
    fallidas = (
        session.scalar(
            select(func.count(Edicion.id)).where(Edicion.missing_at.is_not(None))
        )
        or 0
    )

    jobs_by_status = dict(
        session.execute(
            select(HarvestJob.status, func.count(HarvestJob.id)).group_by(HarvestJob.status)
        ).all()
    )

    return IngestCoverage(
        ediciones=ediciones,
        descubiertas=descubiertas,
        enriquecidas=enriquecidas,
        pendientes=pendientes,
        fallidas=fallidas,
        trabajos_pendientes=int(jobs_by_status.get("pending", 0)),
        trabajos_en_ejecucion=int(jobs_by_status.get("running", 0)),
        trabajos_completados=int(jobs_by_status.get("completed", 0)),
        trabajos_fallidos=int(jobs_by_status.get("failed", 0)),
    )


JobHandler = Callable[[Session, HarvestJob], dict[str, Any] | None]


def _index_handler(session: Session, job: HarvestJob) -> dict[str, Any]:
    from mediateca.catalog.indexer import MeiliIndexer

    total = MeiliIndexer().index_editions(session, reset=False)
    return {"indexed": total}


DEFAULT_HANDLERS: dict[str, JobHandler] = {"index": _index_handler}


def execute_job(
    session: Session,
    job: HarvestJob,
    *,
    handlers: dict[str, JobHandler] | None = None,
) -> dict[str, Any]:
    registry = {**DEFAULT_HANDLERS, **(handlers or {})}
    handler = registry.get(job.job_type)
    if handler is None:
        raise NotImplementedError(
            f"No hay handler para el trabajo '{job.job_type}'. "
            "Se registrara en el cambio de descubrimiento o enriquecimiento."
        )
    return handler(session, job) or {}


def backoff_seconds(attempts: int) -> float:
    return min(5.0 * (2 ** max(0, attempts - 1)), 3600.0)


def _touch_heartbeat_file(path: Path | None) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(int(time.time())), encoding="utf-8")


def _heartbeat_loop(
    factory: sessionmaker[Session],
    job_id: int,
    interval: float,
    stop_event: threading.Event,
    heartbeat_file: Path | None,
) -> None:
    while not stop_event.wait(interval):
        try:
            with factory() as session:
                job = session.get(HarvestJob, job_id)
                if job is not None and job.status == "running":
                    touch_job(session, job)
                    session.commit()
            _touch_heartbeat_file(heartbeat_file)
        except Exception:  # noqa: BLE001
            # El heartbeat no debe tumbar el trabajo principal.
            continue


def worker_tick(
    session: Session,
    *,
    handlers: dict[str, JobHandler] | None = None,
    heartbeat_seconds: float = 0.0,
    heartbeat_file: Path | None = None,
) -> tuple[HarvestJob | None, float]:
    job = claim_job(session)
    if job is None:
        session.commit()
        return None, 0.0

    job_id = job.id
    session.commit()

    stop_event = threading.Event()
    heartbeat_thread: threading.Thread | None = None
    if heartbeat_seconds > 0:
        factory = sessionmaker(
            bind=session.get_bind(), expire_on_commit=False, future=True
        )
        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            args=(factory, job_id, heartbeat_seconds, stop_event, heartbeat_file),
            daemon=True,
        )
        heartbeat_thread.start()

    try:
        stats = execute_job(session, job, handlers=handlers)
        finish_job(session, job, status="completed", stats=stats)
        session.commit()
        return job, 0.0
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        failed_job = session.get(HarvestJob, job_id)
        if failed_job is None:
            return None, 0.0
        if (failed_job.attempts or 0) >= (failed_job.max_attempts or 1):
            finish_job(session, failed_job, status="failed", error=str(exc))
            session.commit()
            return failed_job, 0.0
        requeue_job(session, failed_job, error=str(exc))
        session.commit()
        return failed_job, backoff_seconds(failed_job.attempts)
    finally:
        stop_event.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=1.0)
        _touch_heartbeat_file(heartbeat_file)


def run_worker(
    session_factory: sessionmaker[Session],
    *,
    handlers: dict[str, JobHandler] | None = None,
    poll_seconds: float = 5.0,
    heartbeat_seconds: float = 30.0,
    heartbeat_file: Path | None = None,
    max_iterations: int | None = None,
    stop_event: threading.Event | None = None,
) -> int:
    processed = 0
    while stop_event is None or not stop_event.is_set():
        with session_factory() as session:
            job, backoff = worker_tick(
                session,
                handlers=handlers,
                heartbeat_seconds=heartbeat_seconds,
                heartbeat_file=heartbeat_file,
            )
        _touch_heartbeat_file(heartbeat_file)

        if job is not None:
            processed += 1
            if max_iterations is not None and processed >= max_iterations:
                break

        wait = backoff if backoff > 0 else poll_seconds
        if stop_event is not None:
            stop_event.wait(wait)
        else:
            time.sleep(wait)

    return processed
