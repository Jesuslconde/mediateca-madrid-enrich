from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class IngestJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: str
    status: str
    cursor_doc: int | None = None
    cursor_titn: str | None = None
    batch_size: int
    attempts: int
    max_attempts: int
    stats: dict[str, Any]
    error: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None


class IngestCoverageOut(BaseModel):
    ediciones: int
    descubiertas: int
    enriquecidas: int
    pendientes: int
    fallidas: int
    desaparecidas: int
    porcentaje: int


class IngestMetricsOut(BaseModel):
    processed: int
    errors: int
    captchas: int
    captchas_solved: int
    captchas_failed: int
    session_renewals: int
    failed: int
    pending: int
    average_ms: float | None = None


class WorkerHealthOut(BaseModel):
    status: str
    last_heartbeat: datetime | None = None
    source: str | None = None


class IngestStatusOut(BaseModel):
    jobs: list[IngestJobOut]
    coverage: IngestCoverageOut
    metrics: IngestMetricsOut
    worker: WorkerHealthOut
    generated_at: datetime


class IngestCoverageResponse(BaseModel):
    coverage: IngestCoverageOut
    metrics: IngestMetricsOut
    worker: WorkerHealthOut
    generated_at: datetime
