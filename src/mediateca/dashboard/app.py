from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from mediateca.api.routers.ingest import router as ingest_router
from mediateca.catalog.jobs import ingest_metrics
from mediateca.core.config import settings
from mediateca.core.config_store import (
    FLARESOLVERR_URL_KEY,
    ConfigValidationError,
    normalize_flaresolverr_url,
    set_config_value,
)
from mediateca.core.db import get_session_factory
from mediateca.core.logging import get_logger

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


def get_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def _dashboard_context(session: Session) -> dict[str, Any]:
    cover = catalog_coverage(session)
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
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context=context,
    )


@app.post("/config/flaresolverr")
async def save_flaresolverr_config(
    request: Request,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    body = (await request.body()).decode("utf-8")
    values = parse_qs(body, keep_blank_values=True)
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
