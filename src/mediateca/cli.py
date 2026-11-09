from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

import typer
from mediateca_shared.models import Biblioteca, Edicion, Ejemplar, HarvestJob
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select

from mediateca.catalog.harvester import Harvester, OpacClient
from mediateca.catalog.indexer import MeiliIndexer
from mediateca.catalog.jobs import (
    DEFAULT_HANDLERS,
    coverage,
    run_worker,
    worker_tick,
)
from mediateca.catalog.parser import parse_file
from mediateca.core.config import settings
from mediateca.core.db import get_session_factory, init_db, session_scope
from mediateca.core.logging import configure_logging, get_logger

app = typer.Typer(
    name="mediateca",
    help="Catalogo alternativo de videos y DVD/Blu-ray de Madrid.",
    no_args_is_help=True,
)
console = Console()
logger = get_logger(__name__)


@app.command("init-db")
def init_db_command() -> None:
    """Crea las tablas y el indice de Meilisearch."""
    configure_logging()
    init_db()
    try:
        MeiliIndexer().ensure_index()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]No se pudo inicializar Meilisearch: {exc}[/yellow]")
    console.print("[green]Base de datos e indice inicializados[/green]")


@app.command("harvest")
def harvest_command(
    query: str = typer.Option("cine", "--query", "-q", help="Termino de busqueda"),
    max_pages: int = typer.Option(1, "--max-pages", min=1, help="Paginas maximas"),
    limit: int | None = typer.Option(None, "--limit", min=1, help="Fichas maximas"),
    delay: float = typer.Option(1.0, "--delay", min=0.1, help="Segundos entre peticiones"),
    index: bool = typer.Option(False, "--index", help="Indexar al terminar"),
) -> None:
    """Recolecta fichas del OPAC y las guarda en PostgreSQL."""
    configure_logging()
    with session_scope() as session, OpacClient(delay=delay) as client:
        harvester = Harvester(session, client=client)
        stats = harvester.harvest_query(
            query, max_pages=max_pages, limit=limit, delay=delay
        )
    console.print(f"[green]Recoleccion terminada:[/green] {stats}")
    if index:
        with session_scope() as session:
            total = MeiliIndexer().index_editions(session, reset=False)
        console.print(f"[green]{total} ediciones indexadas[/green]")


@app.command("discover")
def discover_command(
    max_pages: int | None = typer.Option(
        None, "--max-pages", min=1, help="Paginas maximas (todas por defecto)"
    ),
    limit: int | None = typer.Option(None, "--limit", min=1, help="TITN maximos"),
    delay: float = typer.Option(1.0, "--delay", min=0.1, help="Segundos entre peticiones"),
    index: bool = typer.Option(False, "--index", help="Indexar al terminar"),
) -> None:
    """Descubre el catalogo completo y crea ediciones stub."""
    configure_logging()
    with session_scope() as session, OpacClient(delay=delay) as client:
        harvester = Harvester(session, client=client)
        stats = harvester.harvest_discovery(
            max_pages=max_pages, limit=limit, delay=delay
        )
    console.print(f"[green]Descubrimiento terminado:[/green] {stats}")
    if index:
        with session_scope() as session:
            total = MeiliIndexer().index_editions(session, reset=False)
        console.print(f"[green]{total} ediciones indexadas[/green]")


@app.command("enrich")
def enrich_command(
    limit: int = typer.Option(
        5000, "--limit", min=1, help="Fichas maximas por lote"
    ),
    delay: float = typer.Option(1.0, "--delay", min=0.1, help="Segundos entre peticiones"),
) -> None:
    """Enriquece por lotes las ediciones descubiertas y pendientes."""
    configure_logging()
    with session_scope() as session, OpacClient(delay=delay) as client:
        harvester = Harvester(session, client=client)
        stats = harvester.harvest_enrichment(limit=limit, delay=delay)
    console.print(f"[green]Enriquecimiento terminado:[/green] {stats}")


@app.command("index")
def index_command(
    reset: bool = typer.Option(False, "--reset", help="Vaciar el indice antes de cargar"),
) -> None:
    """Construye el indice de Meilisearch desde PostgreSQL."""
    configure_logging()
    with session_scope() as session:
        total = MeiliIndexer().index_editions(session, reset=reset)
    console.print(f"[green]{total} ediciones indexadas[/green]")


@app.command("stats")
def stats_command() -> None:
    """Muestra un resumen del catalogo local."""
    with session_scope() as session:
        ediciones = session.scalar(select(func.count(Edicion.id))) or 0
        ejemplares = session.scalar(select(func.count(Ejemplar.id))) or 0
        bibliotecas = session.scalar(select(func.count(Biblioteca.id))) or 0

        table = Table(title="Mediateca Madrid")
        table.add_column("Metrica")
        table.add_column("Valor", justify="right")
        table.add_row("Ediciones", str(ediciones))
        table.add_row("Ejemplares", str(ejemplares))
        table.add_row("Bibliotecas", str(bibliotecas))
        console.print(table)


@app.command("status")
def status_command(
    limit: int = typer.Option(20, "--limit", min=1, help="Trabajos a mostrar"),
) -> None:
    """Muestra los trabajos de ingesta y la cobertura del catalogo."""
    with session_scope() as session:
        jobs = list(
            session.scalars(
                select(HarvestJob).order_by(HarvestJob.created_at.desc()).limit(limit)
            )
        )
        cover = coverage(session)

    jobs_table = Table(title="Trabajos de ingesta")
    for column in ("ID", "Tipo", "Estado", "Intentos", "Cursor", "Inicio", "Heartbeat"):
        jobs_table.add_column(column)
    for job in jobs:
        cursor = f"{job.cursor_doc or '—'}/{job.cursor_titn or '—'}"
        started = job.started_at.strftime("%Y-%m-%d %H:%M") if job.started_at else "—"
        heartbeat = (
            job.heartbeat_at.strftime("%Y-%m-%d %H:%M") if job.heartbeat_at else "—"
        )
        jobs_table.add_row(
            str(job.id),
            job.job_type,
            job.status,
            f"{job.attempts}/{job.max_attempts}",
            cursor,
            started,
            heartbeat,
        )
    console.print(jobs_table)

    coverage_table = Table(title="Cobertura del catalogo")
    coverage_table.add_column("Metrica")
    coverage_table.add_column("Valor", justify="right")
    coverage_table.add_row("Ediciones", str(cover.ediciones))
    coverage_table.add_row("Descubiertas", str(cover.descubiertas))
    coverage_table.add_row("Enriquecidas", str(cover.enriquecidas))
    coverage_table.add_row("Pendientes", str(cover.pendientes))
    coverage_table.add_row("Fallidas", str(cover.fallidas))
    coverage_table.add_row("Trabajos pendientes", str(cover.trabajos_pendientes))
    coverage_table.add_row("Trabajos en ejecucion", str(cover.trabajos_en_ejecucion))
    coverage_table.add_row("Trabajos completados", str(cover.trabajos_completados))
    coverage_table.add_row("Trabajos fallidos", str(cover.trabajos_fallidos))
    console.print(coverage_table)


@app.command("worker")
def worker_command(
    once: bool = typer.Option(False, "--once", help="Procesa un trabajo y termina"),
    poll: float = typer.Option(settings.worker_poll_seconds, "--poll", min=0.1),
    heartbeat: float = typer.Option(
        settings.worker_heartbeat_seconds, "--heartbeat", min=0.0
    ),
) -> None:
    """Reclama y ejecuta trabajos de la cola de ingesta."""
    configure_logging()

    if once:
        with session_scope() as session:
            job, backoff = worker_tick(
                session,
                handlers=DEFAULT_HANDLERS,
                heartbeat_seconds=heartbeat,
                heartbeat_file=settings.worker_heartbeat_file,
            )
        if job is None:
            console.print("[yellow]No hay trabajos pendientes[/yellow]")
        else:
            console.print(
                f"[green]Trabajo {job.id} ({job.job_type}) {job.status}[/green]"
                f" backoff={backoff:.0f}s"
            )
        return

    factory = get_session_factory()
    concurrency = max(1, settings.worker_concurrency)
    console.print(f"[green]Worker iniciado[/green] concurrencia={concurrency}")
    threads = [
        threading.Thread(
            target=run_worker,
            kwargs={
                "session_factory": factory,
                "handlers": DEFAULT_HANDLERS,
                "poll_seconds": poll,
                "heartbeat_seconds": heartbeat,
                "heartbeat_file": settings.worker_heartbeat_file,
            },
            daemon=True,
        )
        for _ in range(concurrency)
    ]
    for thread in threads:
        thread.start()
    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        console.print("Worker detenido")


@app.command("parse-file")
def parse_file_command(path: Path = typer.Argument(..., exists=True)) -> None:
    """Parsea una ficha HTML local y muestra el JSON resultante."""
    parsed = parse_file(str(path), url=str(path))
    console.print_json(json.dumps(asdict(parsed), ensure_ascii=False, default=str))


def _run_harvest_job() -> None:
    logger.info("Iniciando recoleccion programada")
    try:
        for query in settings.queries:
            with session_scope() as session, OpacClient() as client:
                harvester = Harvester(session, client=client)
                stats = harvester.harvest_query(query, max_pages=2)
                logger.info("Recoleccion %s: %s", query, stats)
        with session_scope() as session:
            total = MeiliIndexer().index_editions(session)
        logger.info("Indexadas %s ediciones", total)
    except Exception:  # noqa: BLE001
        logger.exception("Fallo la recoleccion programada")


@app.command("scheduler")
def scheduler_command() -> None:
    """Ejecuta la recoleccion de fichas periodicamente."""
    from apscheduler.schedulers.blocking import BlockingScheduler

    configure_logging()
    try:
        MeiliIndexer().ensure_index()
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo preparar Meilisearch")

    scheduler = BlockingScheduler(timezone="Europe/Madrid")
    now = datetime.now() + timedelta(minutes=1)
    scheduler.add_job(
        _run_harvest_job,
        "interval",
        hours=settings.scheduler_harvest_hours,
        next_run_time=now,
        id="harvest",
    )
    console.print("[green]Scheduler iniciado[/green]")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        console.print("Scheduler detenido")


if __name__ == "__main__":
    app()
