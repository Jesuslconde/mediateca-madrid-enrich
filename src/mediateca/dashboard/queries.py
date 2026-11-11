from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from mediateca_shared.constants import JOB_STATUSES, JOB_TYPES
from mediateca_shared.models import HarvestJob
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mediateca.catalog.jobs import IngestCoverage, coverage
from mediateca.core.config import settings
from mediateca.core.config_store import (
    FLARESOLVERR_URL_KEY,
    TMDB_API_TOKEN_KEY,
    ConfigValidationError,
    get_config_value,
    normalize_flaresolverr_url,
    normalize_tmdb_api_token,
)


@dataclass(slots=True)
class WorkerHealth:
    status: str
    last_heartbeat: datetime | None
    source: str | None


@dataclass(slots=True)
class FlareSolverrConfig:
    saved_url: str | None
    env_url: str | None
    effective_url: str | None
    source: str
    active: bool


@dataclass(slots=True)
class TmdbConfig:
    saved: bool
    env: bool
    effective: bool
    source: str
    masked_token: str | None
    active: bool


def _normalize_or_none(value: str | None) -> str | None:
    try:
        return normalize_flaresolverr_url(value)
    except ConfigValidationError:
        return None


def flaresolverr_config(session: Session) -> FlareSolverrConfig:
    saved = _normalize_or_none(get_config_value(session, FLARESOLVERR_URL_KEY))
    env = _normalize_or_none(settings.flaresolverr_url)

    if saved:
        return FlareSolverrConfig(
            saved_url=saved,
            env_url=env,
            effective_url=saved,
            source="dashboard",
            active=True,
        )
    if env:
        return FlareSolverrConfig(
            saved_url=None,
            env_url=env,
            effective_url=env,
            source="entorno",
            active=True,
        )
    return FlareSolverrConfig(
        saved_url=None,
        env_url=None,
        effective_url=None,
        source="ninguno",
        active=False,
    )


def _normalize_tmdb(value: str | None) -> str | None:
    try:
        return normalize_tmdb_api_token(value)
    except ConfigValidationError:
        return None


def _mask_token(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 4:
        return "****"
    return "****" + value[-4:]


def tmdb_config(session: Session) -> TmdbConfig:
    saved = _normalize_tmdb(get_config_value(session, TMDB_API_TOKEN_KEY))
    env = _normalize_tmdb(settings.tmdb_api_token)

    if saved:
        return TmdbConfig(
            saved=True,
            env=bool(env),
            effective=True,
            source="dashboard",
            masked_token=_mask_token(saved),
            active=True,
        )
    if env:
        return TmdbConfig(
            saved=False,
            env=True,
            effective=True,
            source="entorno",
            masked_token=_mask_token(env),
            active=True,
        )
    return TmdbConfig(
        saved=False,
        env=False,
        effective=False,
        source="ninguno",
        masked_token=None,
        active=False,
    )


def job_status_counts(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(HarvestJob.status, func.count(HarvestJob.id)).group_by(HarvestJob.status)
    ).all()
    counts = {status: 0 for status in JOB_STATUSES}
    for status, total in rows:
        counts[str(status)] = int(total)
    return counts


def job_type_counts(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(HarvestJob.job_type, func.count(HarvestJob.id)).group_by(
            HarvestJob.job_type
        )
    ).all()
    counts = {job_type: 0 for job_type in JOB_TYPES}
    for job_type, total in rows:
        counts[str(job_type)] = int(total)
    return counts


def recent_jobs(session: Session, limit: int | None = None) -> list[HarvestJob]:
    limit = settings.dashboard_recent_limit if limit is None else limit
    stmt = (
        select(HarvestJob)
        .order_by(HarvestJob.created_at.desc(), HarvestJob.id.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def worker_health(
    session: Session,
    *,
    now: datetime | None = None,
    heartbeat_file: Path | None = None,
    stale_seconds: int | None = None,
) -> WorkerHealth:
    path = heartbeat_file if heartbeat_file is not None else settings.worker_heartbeat_file
    stale = (
        stale_seconds
        if stale_seconds is not None
        else settings.dashboard_worker_stale_seconds
    )
    current = now or datetime.now(UTC)

    last_heartbeat: datetime | None = None
    source: str | None = None
    try:
        modified = path.stat().st_mtime
    except OSError:
        pass
    else:
        last_heartbeat = datetime.fromtimestamp(modified, tz=UTC)
        source = "file"

    if last_heartbeat is None:
        db_heartbeat = session.scalar(
            select(func.max(HarvestJob.heartbeat_at)).where(
                HarvestJob.status == "running"
            )
        )
        if db_heartbeat is not None:
            last_heartbeat = (
                db_heartbeat
                if db_heartbeat.tzinfo is not None
                else db_heartbeat.replace(tzinfo=UTC)
            )
            source = "database"

    if last_heartbeat is None:
        return WorkerHealth(status="degraded", last_heartbeat=None, source=None)

    age = (current - last_heartbeat).total_seconds()
    status = "ok" if age <= stale else "degraded"
    return WorkerHealth(status=status, last_heartbeat=last_heartbeat, source=source)


def enrichment_percentage(cover: IngestCoverage) -> int:
    if cover.ediciones <= 0:
        return 0
    return round(cover.enriquecidas * 100 / cover.ediciones)


def catalog_coverage(session: Session) -> IngestCoverage:
    return coverage(session)
