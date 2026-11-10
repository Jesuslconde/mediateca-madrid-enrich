from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from mediateca_shared.constants import JOB_TYPES
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from mediateca.api.routers.ingest import router as ingest_router
from mediateca.catalog.jobs import (
    JobAlreadyActive,
    enqueue_discover_job,
    enqueue_enrich_job,
    enqueue_index_job,
    has_active_job,
    ingest_metrics,
)
from mediateca.catalog.repository import count_pending_titns
from mediateca.core.config import settings
from mediateca.core.config_store import (
    FLARESOLVERR_URL_KEY,
    ConfigValidationError,
    normalize_flaresolverr_url,
    set_config_value,
)
from mediateca.core.db import get_session_factory
from mediateca.core.logging import get_logger
from mediateca.core.scheduling import (
    ScheduleSettings,
    ScheduleValidationError,
    build_schedule_status,
    load_schedule_settings,
    save_schedule_settings,
)

from .queries import (
    catalog_coverage,
    enrichment_percentage,
    flaresolverr_config,
    job_status_counts,
    job_type_counts,
    recent_jobs,
    worker_health,
)

logger = get_logger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

DEGRADED_MESSAGE = (
    "No se pudo leer el estado de la ingesta. "
    "Revisa la conexion con la base de datos y vuelve a intentarlo."
)

ADMIN_COOKIE = "mediateca_admin"
ADMIN_COOKIE_MAX_AGE = 8 * 60 * 60


def _has_write_access(request: Request) -> bool:
    token = settings.dashboard_admin_token
    if not token:
        return True
    provided = request.cookies.get(ADMIN_COOKIE) or request.headers.get("X-Admin-Token")
    return provided == token


def _admin_error() -> RedirectResponse:
    return RedirectResponse(
        f"/?{urlencode({'error': 'Token de administracion requerido o incorrecto'})}",
        status_code=303,
    )


async def _form_values(request: Request) -> dict[str, list[str]]:
    body = (await request.body()).decode("utf-8")
    return parse_qs(body, keep_blank_values=True)


def _form_int(
    values: dict[str, list[str]], name: str, default: int
) -> int:
    raw = (values.get(name) or [str(default)])[0].strip()
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ScheduleValidationError(f"El campo {name} debe ser un numero") from exc


def get_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def _dashboard_context(session: Session) -> dict[str, Any]:
    cover = catalog_coverage(session)
    schedule = load_schedule_settings(session)
    return {
        "refresh_seconds": settings.dashboard_refresh_seconds,
        "status_counts": job_status_counts(session),
        "type_counts": job_type_counts(session),
        "jobs": recent_jobs(session),
        "coverage": cover,
        "enrichment_percent": enrichment_percentage(cover),
        "metrics": ingest_metrics(session, cover),
        "worker": worker_health(session),
        "flaresolverr": flaresolverr_config(session),
        "schedule": schedule,
        "schedule_status": build_schedule_status(session, schedule),
        "active_jobs": {job_type: has_active_job(session, job_type) for job_type in JOB_TYPES},
        "pending_titns": count_pending_titns(session),
        "generated_at": datetime.now(UTC),
    }


app = FastAPI(
    title="Mediateca Madrid - Estado de la ingesta",
    description="Vista de estado y API de observabilidad de la ingesta.",
)
app.include_router(ingest_router, prefix="/api")


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    try:
        context = _dashboard_context(session)
    except SQLAlchemyError:
        logger.exception("No se pudo leer el estado de la ingesta")
        return templates.TemplateResponse(
            request=request,
            name="degraded.html",
            context={
                "message": DEGRADED_MESSAGE,
                "refresh_seconds": settings.dashboard_refresh_seconds,
                "generated_at": datetime.now(UTC),
            },
        )
    context["message"] = request.query_params.get("message")
    context["error"] = request.query_params.get("error")
    context["admin_required"] = bool(settings.dashboard_admin_token)
    context["is_admin"] = _has_write_access(request)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context=context,
    )


@app.post("/admin/login")
async def admin_login(
    request: Request,
) -> RedirectResponse:
    if not settings.dashboard_admin_token:
        return RedirectResponse(
            f"/?{urlencode({'error': 'No hay token de administracion configurado'})}",
            status_code=303,
        )
    values = await _form_values(request)
    token = (values.get("token") or [""])[0].strip()
    if token != settings.dashboard_admin_token:
        return _admin_error()
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        ADMIN_COOKIE,
        token,
        max_age=ADMIN_COOKIE_MAX_AGE,
        httponly=True,
        samesite="strict",
    )
    return response


@app.post("/admin/logout")
async def admin_logout() -> RedirectResponse:
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(ADMIN_COOKIE)
    return response


@app.post("/config/schedule")
async def save_schedule_config(
    request: Request,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    if not _has_write_access(request):
        return _admin_error()
    values = await _form_values(request)
    try:
        schedule = ScheduleSettings(
            enabled=(values.get("enabled") or ["false"])[0].lower()
            in {"1", "true", "on", "yes", "si", "sí"},
            discover_interval_hours=_form_int(values, "discover_interval_hours", 12),
            full_sweep_interval_hours=_form_int(
                values, "full_sweep_interval_hours", 168
            ),
            enrich_interval_hours=_form_int(values, "enrich_interval_hours", 12),
            enrich_batch_size=_form_int(values, "enrich_batch_size", 5000),
        )
        save_schedule_settings(session, schedule)
        session.commit()
    except ScheduleValidationError as exc:
        session.rollback()
        return RedirectResponse(
            f"/?{urlencode({'error': str(exc)})}",
            status_code=303,
        )
    except SQLAlchemyError:
        session.rollback()
        logger.exception("No se pudo guardar la programacion de ingesta")
        return RedirectResponse(
            f"/?{urlencode({'error': 'No se pudo guardar la programacion de ingesta'})}",
            status_code=303,
        )
    return RedirectResponse(
        f"/?{urlencode({'message': 'Programacion guardada'})}",
        status_code=303,
    )


@app.post("/jobs")
async def enqueue_job_from_dashboard(
    request: Request,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    if not _has_write_access(request):
        return _admin_error()
    values = await _form_values(request)
    job_type = (values.get("job_type") or [""])[0].strip()
    try:
        if job_type == "discover":
            mode = (values.get("mode") or ["incremental"])[0].strip()
            job = enqueue_discover_job(session, mode=mode, reason="dashboard")
        elif job_type == "enrich":
            limit = int((values.get("limit") or ["5000"])[0])
            if not 1 <= limit <= 50000:
                raise ValueError("El lote debe estar entre 1 y 50000")
            job = enqueue_enrich_job(
                session,
                batch_size=limit,
                since=None,
                reason="dashboard",
            )
        elif job_type == "index":
            job = enqueue_index_job(session)
        else:
            raise ValueError("Tipo de trabajo no valido")
        session.commit()
    except JobAlreadyActive as exc:
        session.rollback()
        return RedirectResponse(
            f"/?{urlencode({'error': str(exc)})}",
            status_code=303,
        )
    except (ValueError, SQLAlchemyError) as exc:
        session.rollback()
        logger.exception("No se pudo encolar el trabajo desde el dashboard")
        return RedirectResponse(
            f"/?{urlencode({'error': str(exc)})}",
            status_code=303,
        )
    return RedirectResponse(
        f"/?{urlencode({'message': f'Trabajo {job.id} ({job.job_type}) encolado'})}",
        status_code=303,
    )


@app.post("/config/flaresolverr")
async def save_flaresolverr_config(
    request: Request,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    if not _has_write_access(request):
        return _admin_error()
    values = await _form_values(request)
    url = (values.get("url") or [""])[0]

    try:
        normalized = normalize_flaresolverr_url(url)
        set_config_value(session, FLARESOLVERR_URL_KEY, normalized)
        session.commit()
    except ConfigValidationError as exc:
        session.rollback()
        return RedirectResponse(
            f"/?{urlencode({'error': str(exc)})}",
            status_code=303,
        )
    except SQLAlchemyError:
        session.rollback()
        logger.exception("No se pudo guardar la configuracion de FlareSolverr")
        return RedirectResponse(
            f"/?{urlencode({'error': 'No se pudo guardar la configuracion de FlareSolverr'})}",
            status_code=303,
        )

    message = (
        "Configuracion de FlareSolverr guardada"
        if normalized
        else "Configuracion de FlareSolverr eliminada"
    )
    return RedirectResponse(f"/?{urlencode({'message': message})}", status_code=303)


@app.get("/health")
def health(session: Session = Depends(get_session)) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("La base de datos no responde al healthcheck del dashboard")
        return {"status": "degraded", "db": "error"}
    return {"status": "ok", "db": "ok"}
