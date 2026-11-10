from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from mediateca_shared.models import HarvestJob
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mediateca.core.config import settings
from mediateca.core.config_store import get_config_value, set_config_value
from mediateca.core.logging import get_logger

logger = get_logger(__name__)

SCHEDULER_ENABLED_KEY = "scheduler_enabled"
DISCOVER_INTERVAL_HOURS_KEY = "discover_interval_hours"
FULL_SWEEP_INTERVAL_HOURS_KEY = "full_sweep_interval_hours"
ENRICH_INTERVAL_HOURS_KEY = "enrich_interval_hours"
ENRICH_BATCH_SIZE_KEY = "enrich_batch_size"

MIN_INTERVAL_HOURS = 1
MAX_INTERVAL_HOURS = 24 * 30
MAX_FULL_SWEEP_HOURS = 24 * 365
MIN_BATCH_SIZE = 1
MAX_BATCH_SIZE = 50000


class ScheduleValidationError(ValueError):
    pass


@dataclass(slots=True)
class ScheduleSettings:
    enabled: bool
    discover_interval_hours: int
    full_sweep_interval_hours: int
    enrich_interval_hours: int
    enrich_batch_size: int


@dataclass(slots=True)
class ScheduledTaskStatus:
    last_run: datetime | None
    next_run: datetime | None
    active: bool


@dataclass(slots=True)
class ScheduleStatus:
    discover: ScheduledTaskStatus
    full_sweep: ScheduledTaskStatus
    enrich: ScheduledTaskStatus


def default_schedule_settings() -> ScheduleSettings:
    return ScheduleSettings(
        enabled=settings.scheduler_enabled,
        discover_interval_hours=12,
        full_sweep_interval_hours=168,
        enrich_interval_hours=12,
        enrich_batch_size=5000,
    )


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def _parse_int(value: str | None, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def load_schedule_settings(session: Session) -> ScheduleSettings:
    defaults = default_schedule_settings()
    return ScheduleSettings(
        enabled=_parse_bool(
            get_config_value(session, SCHEDULER_ENABLED_KEY),
            defaults.enabled,
        ),
        discover_interval_hours=_parse_int(
            get_config_value(session, DISCOVER_INTERVAL_HOURS_KEY),
            defaults.discover_interval_hours,
            MIN_INTERVAL_HOURS,
            MAX_INTERVAL_HOURS,
        ),
        full_sweep_interval_hours=_parse_int(
            get_config_value(session, FULL_SWEEP_INTERVAL_HOURS_KEY),
            defaults.full_sweep_interval_hours,
            0,
            MAX_FULL_SWEEP_HOURS,
        ),
        enrich_interval_hours=_parse_int(
            get_config_value(session, ENRICH_INTERVAL_HOURS_KEY),
            defaults.enrich_interval_hours,
            MIN_INTERVAL_HOURS,
            MAX_INTERVAL_HOURS,
        ),
        enrich_batch_size=_parse_int(
            get_config_value(session, ENRICH_BATCH_SIZE_KEY),
            defaults.enrich_batch_size,
            MIN_BATCH_SIZE,
            MAX_BATCH_SIZE,
        ),
    )


def validate_schedule_settings(settings_to_save: ScheduleSettings) -> None:
    if not MIN_INTERVAL_HOURS <= settings_to_save.discover_interval_hours <= MAX_INTERVAL_HOURS:
        raise ScheduleValidationError(
            f"El intervalo de descubrimiento debe estar entre {MIN_INTERVAL_HOURS} y "
            f"{MAX_INTERVAL_HOURS} horas"
        )
    if not 0 <= settings_to_save.full_sweep_interval_hours <= MAX_FULL_SWEEP_HOURS:
        raise ScheduleValidationError(
            f"El barrido completo debe estar entre 0 y {MAX_FULL_SWEEP_HOURS} horas"
        )
    if not MIN_INTERVAL_HOURS <= settings_to_save.enrich_interval_hours <= MAX_INTERVAL_HOURS:
        raise ScheduleValidationError(
            f"El intervalo de enriquecimiento debe estar entre {MIN_INTERVAL_HOURS} y "
            f"{MAX_INTERVAL_HOURS} horas"
        )
    if not MIN_BATCH_SIZE <= settings_to_save.enrich_batch_size <= MAX_BATCH_SIZE:
        raise ScheduleValidationError(
            f"El lote de enriquecimiento debe estar entre {MIN_BATCH_SIZE} y "
            f"{MAX_BATCH_SIZE}"
        )


def save_schedule_settings(session: Session, settings_to_save: ScheduleSettings) -> None:
    validate_schedule_settings(settings_to_save)
    set_config_value(
        session,
        SCHEDULER_ENABLED_KEY,
        "true" if settings_to_save.enabled else "false",
    )
    set_config_value(
        session,
        DISCOVER_INTERVAL_HOURS_KEY,
        str(settings_to_save.discover_interval_hours),
    )
    set_config_value(
        session,
        FULL_SWEEP_INTERVAL_HOURS_KEY,
        str(settings_to_save.full_sweep_interval_hours),
    )
    set_config_value(
        session,
        ENRICH_INTERVAL_HOURS_KEY,
        str(settings_to_save.enrich_interval_hours),
    )
    set_config_value(
        session,
        ENRICH_BATCH_SIZE_KEY,
        str(settings_to_save.enrich_batch_size),
    )
    session.flush()


def last_job(
    session: Session,
    job_type: str,
    *,
    statuses: tuple[str, ...] | None = None,
) -> HarvestJob | None:
    stmt = select(HarvestJob).where(HarvestJob.job_type == job_type)
    if statuses:
        stmt = stmt.where(HarvestJob.status.in_(statuses))
    stmt = stmt.order_by(HarvestJob.created_at.desc(), HarvestJob.id.desc()).limit(1)
    return session.scalars(stmt).first()


def last_completed_discover(session: Session) -> HarvestJob | None:
    return last_job(session, "discover", statuses=("completed",))


def last_full_discover(session: Session) -> HarvestJob | None:
    stmt = (
        select(HarvestJob)
        .where(HarvestJob.job_type == "discover")
        .order_by(HarvestJob.created_at.desc(), HarvestJob.id.desc())
        .limit(200)
    )
    for job in session.scalars(stmt):
        mode = (job.stats or {}).get("mode")
        if mode == "full" or mode is None:
            return job
    return None


def has_active_job(session: Session, job_type: str) -> bool:
    total = session.scalar(
        select(func.count(HarvestJob.id)).where(
            HarvestJob.job_type == job_type,
            HarvestJob.status.in_(("pending", "running")),
        )
    )
    return bool(total)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _next_run(job: HarvestJob | None, hours: int) -> datetime | None:
    if job is None or job.created_at is None or hours <= 0:
        return None
    created = _as_aware(job.created_at)
    assert created is not None
    return created + timedelta(hours=hours)


def build_schedule_status(
    session: Session,
    settings_to_show: ScheduleSettings | None = None,
    *,
    now: datetime | None = None,
) -> ScheduleStatus:
    current = now or datetime.now(UTC)
    schedule = settings_to_show or load_schedule_settings(session)
    last_discover = last_job(session, "discover")
    last_full = last_full_discover(session)
    last_enrich = last_job(session, "enrich")

    discover_next = _next_run(last_discover, schedule.discover_interval_hours)
    if discover_next is None and schedule.enabled:
        discover_next = current
    full_next = _next_run(last_full, schedule.full_sweep_interval_hours)
    if full_next is None and schedule.enabled and schedule.full_sweep_interval_hours > 0:
        full_next = current
    enrich_next = _next_run(last_enrich, schedule.enrich_interval_hours)
    if enrich_next is None and schedule.enabled:
        enrich_next = current

    def task(
        job: HarvestJob | None, next_run: datetime | None, job_type: str
    ) -> ScheduledTaskStatus:
        return ScheduledTaskStatus(
            last_run=_as_aware(job.created_at) if job else None,
            next_run=next_run,
            active=has_active_job(session, job_type),
        )

    return ScheduleStatus(
        discover=task(last_discover, discover_next, "discover"),
        full_sweep=task(last_full, full_next, "discover"),
        enrich=task(last_enrich, enrich_next, "enrich"),
    )
