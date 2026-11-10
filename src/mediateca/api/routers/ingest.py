from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from mediateca.api.schemas import (
    IngestCoverageOut,
    IngestCoverageResponse,
    IngestJobOut,
    IngestMetricsOut,
    IngestStatusOut,
    WorkerHealthOut,
)
from mediateca.catalog.jobs import (
    IngestCoverage,
    IngestMetrics,
    WorkerState,
    coverage,
    ingest_metrics,
    recent_jobs,
    worker_state,
)
from mediateca.core.db import get_session_factory

router = APIRouter(prefix="/ingest", tags=["Ingest"])


def get_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def _coverage_out(cover: IngestCoverage, metrics: IngestMetrics) -> IngestCoverageOut:
    return IngestCoverageOut(
        ediciones=cover.ediciones,
        descubiertas=cover.descubiertas,
        enriquecidas=cover.enriquecidas,
        pendientes=cover.pendientes,
        fallidas=metrics.failed,
        desaparecidas=cover.fallidas,
        porcentaje=(
            round(cover.enriquecidas * 100 / cover.ediciones)
            if cover.ediciones
            else 0
        ),
    )


def _metrics_out(metrics: IngestMetrics) -> IngestMetricsOut:
    return IngestMetricsOut(
        processed=metrics.processed,
        errors=metrics.errors,
        captchas=metrics.captchas,
        captchas_solved=metrics.captchas_solved,
        captchas_failed=metrics.captchas_failed,
        session_renewals=metrics.session_renewals,
        failed=metrics.failed,
        pending=metrics.pending,
        average_ms=metrics.average_ms,
    )


def _worker_out(worker: WorkerState) -> WorkerHealthOut:
    return WorkerHealthOut(
        status=worker.status,
        last_heartbeat=worker.last_heartbeat,
        source=worker.source,
    )


@router.get("/status", response_model=IngestStatusOut)
def ingest_status(
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> IngestStatusOut:
    try:
        cover = coverage(session)
        metrics = ingest_metrics(session, cover)
        jobs = [
            IngestJobOut.model_validate(job) for job in recent_jobs(session, limit)
        ]
        worker = worker_state(session)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503, detail="Estado de ingesta no disponible"
        ) from exc

    return IngestStatusOut(
        jobs=jobs,
        coverage=_coverage_out(cover, metrics),
        metrics=_metrics_out(metrics),
        worker=_worker_out(worker),
        generated_at=datetime.now(UTC),
    )


@router.get("/coverage", response_model=IngestCoverageResponse)
def ingest_coverage(
    session: Session = Depends(get_session),
) -> IngestCoverageResponse:
    try:
        cover = coverage(session)
        metrics = ingest_metrics(session, cover)
        worker = worker_state(session)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503, detail="Cobertura de ingesta no disponible"
        ) from exc

    return IngestCoverageResponse(
        coverage=_coverage_out(cover, metrics),
        metrics=_metrics_out(metrics),
        worker=_worker_out(worker),
        generated_at=datetime.now(UTC),
    )
