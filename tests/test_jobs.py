from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from mediateca_shared.models import Edicion, HarvestJob
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mediateca.catalog.harvester import CaptchaRequired
from mediateca.catalog.jobs import (
    _enrich_handler,
    claim_job,
    coverage,
    create_job,
    create_stub,
    finish_job,
    mark_enriched,
    recover_stale_jobs,
    requeue_job,
    touch_job,
    worker_tick,
)
from mediateca.core.db import Base
from mediateca.core.scheduling import ScheduleSettings, save_schedule_settings


def _session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_trabajo_pasa_de_pending_a_completed() -> None:
    session = _session()
    job = create_job(session, "enrich", batch_size=10)
    session.commit()

    assert job.status == "pending"
    assert job.attempts == 0

    claimed = claim_job(session)
    session.commit()

    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == "running"
    assert claimed.attempts == 1
    assert claimed.started_at is not None
    assert claimed.heartbeat_at is not None

    finish_job(session, claimed, stats={"processed": 10})
    session.commit()

    assert claimed.status == "completed"
    assert claimed.finished_at is not None
    assert claimed.stats == {"processed": 10}


def test_reclamo_sin_trabajos_devuelve_none() -> None:
    session = _session()
    assert claim_job(session) is None


def test_un_trabajo_reclamado_no_se_reclama_dos_veces() -> None:
    session = _session()
    create_job(session, "discover")
    session.commit()

    first = claim_job(session)
    session.commit()
    second = claim_job(session)

    assert first is not None
    assert second is None


def test_heartbeat_actualiza_marca_temporal() -> None:
    session = _session()
    create_job(session, "enrich")
    session.commit()

    start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    job = claim_job(session, now=start)
    session.commit()
    assert job is not None
    assert job.heartbeat_at == start

    later = start + timedelta(seconds=30)
    touch_job(session, job, now=later)
    session.commit()

    assert job.heartbeat_at == later


def test_requeue_conserva_intentos_y_permite_reclamar() -> None:
    session = _session()
    create_job(session, "enrich")
    session.commit()

    job = claim_job(session)
    session.commit()
    assert job is not None

    requeue_job(session, job, error="fallo temporal")
    session.commit()
    assert job.status == "pending"
    assert job.started_at is None
    assert job.error == "fallo temporal"
    assert job.attempts == 1

    again = claim_job(session)
    session.commit()
    assert again is not None
    assert again.id == job.id
    assert again.attempts == 2


def test_stub_pasa_a_enriquecida_sin_duplicarse() -> None:
    session = _session()
    first = create_stub(session, "2101557")
    second = create_stub(session, "2101557")
    session.commit()

    assert first.id == second.id
    assert session.scalar(select(func.count(Edicion.id))) == 1
    assert first.is_stub is True
    assert first.discovery_seen_at is not None
    assert first.detail_fetched_at is None

    mark_enriched(session, first)
    session.commit()

    assert first.is_stub is False
    assert first.detail_fetched_at is not None


def test_cobertura_cuenta_ediciones_y_trabajos() -> None:
    session = _session()
    create_stub(session, "1")
    enriched = create_stub(session, "2")
    mark_enriched(session, enriched)

    create_job(session, "discover")
    create_job(session, "enrich")
    failed = create_job(session, "index")
    session.commit()
    claim_job(session)
    session.commit()
    finish_job(session, failed, status="failed", error="boom")
    session.commit()

    cover = coverage(session)

    assert cover.ediciones == 2
    assert cover.descubiertas == 2
    assert cover.enriquecidas == 1
    assert cover.pendientes == 1
    assert cover.fallidas == 0
    assert cover.trabajos_pendientes == 1
    assert cover.trabajos_en_ejecucion == 1
    assert cover.trabajos_completados == 0
    assert cover.trabajos_fallidos == 1
    assert session.scalar(select(func.count(HarvestJob.id))) == 3


def test_worker_tick_procesa_un_trabajo() -> None:
    session = _session()
    create_job(session, "enrich")
    session.commit()
    seen: list[str] = []

    def handler(session, job):  # noqa: ANN001, ANN202
        seen.append(job.job_type)
        return {"processed": 1}

    job, backoff = worker_tick(session, handlers={"enrich": handler})
    session.commit()

    assert job is not None
    assert job.status == "completed"
    assert job.stats == {"processed": 1}
    assert backoff == 0.0
    assert seen == ["enrich"]


def test_worker_ejecuta_el_handler_discover(monkeypatch) -> None:
    import mediateca.catalog.harvester as harvester_module

    session = _session()
    job = create_job(session, "discover", cursor_doc=10, cursor_titn="123")
    session.commit()

    visto: dict[str, int] = {}

    class FakeOpacClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

    class FakeHarvester:
        def __init__(self, session, client) -> None:
            pass

        def harvest_discovery(self, *, job):  # noqa: ANN001
            visto["job_id"] = job.id
            assert job.cursor_doc == 10
            assert job.cursor_titn == "123"
            return {"processed": 2}

    monkeypatch.setattr(harvester_module, "OpacClient", FakeOpacClient)
    monkeypatch.setattr(harvester_module, "Harvester", FakeHarvester)

    processed, backoff = worker_tick(session)
    session.commit()

    assert processed is not None
    assert processed.id == job.id
    assert processed.status == "completed"
    assert processed.stats == {"processed": 2}
    assert visto["job_id"] == job.id
    assert backoff == 0.0


def test_worker_ejecuta_el_handler_enrich(monkeypatch) -> None:
    import mediateca.catalog.harvester as harvester_module

    session = _session()
    job = create_job(session, "enrich", batch_size=5000)
    session.commit()

    visto: dict[str, int] = {}

    class FakeOpacClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

    class FakeHarvester:
        def __init__(self, session, client) -> None:
            pass

        def harvest_enrichment(self, *, job):  # noqa: ANN001
            visto["job_id"] = job.id
            assert job.batch_size == 5000
            return {"processed": 3}

    monkeypatch.setattr(harvester_module, "OpacClient", FakeOpacClient)
    monkeypatch.setattr(harvester_module, "Harvester", FakeHarvester)

    processed, backoff = worker_tick(session)
    session.commit()

    assert processed is not None
    assert processed.id == job.id
    assert processed.status == "completed"
    assert processed.stats == {"processed": 3}
    assert visto["job_id"] == job.id
    assert backoff == 0.0


def test_worker_tick_reintenta_y_termina_en_failed() -> None:
    session = _session()
    create_job(session, "enrich", max_attempts=2)
    session.commit()

    def handler(session, job):  # noqa: ANN001, ANN202
        raise RuntimeError("fallo temporal")

    first, backoff = worker_tick(session, handlers={"enrich": handler})
    session.commit()
    assert first is not None
    assert first.status == "pending"
    assert first.attempts == 1
    assert backoff > 0

    second, backoff = worker_tick(session, handlers={"enrich": handler})
    session.commit()
    assert second is not None
    assert second.status == "failed"
    assert second.attempts == 2
    assert second.error is not None
    assert backoff == 0.0


def test_reclamo_usa_skip_locked_en_postgresql() -> None:
    stmt = (
        select(HarvestJob)
        .where(HarvestJob.status == "pending")
        .with_for_update(skip_locked=True)
    )
    sql = str(stmt.compile(dialect=postgresql.dialect()))

    assert "FOR UPDATE SKIP LOCKED" in sql


def test_worker_indexa_el_lote_al_terminar(monkeypatch) -> None:
    import mediateca.catalog.harvester as harvester_module
    import mediateca.catalog.indexer as indexer_module

    session = _session()
    create_job(session, "enrich", batch_size=10)
    session.commit()

    class FakeOpacClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

    class FakeHarvester:
        def __init__(self, session, client) -> None:
            pass

        def harvest_enrichment(self, *, job):  # noqa: ANN001
            return {"processed": 2, "processed_titns": ["1", "2"]}

    class FakeIndexer:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def index_titns(self, session, titns):  # noqa: ANN001
            self.calls.append(list(titns))
            return len(titns)

    fake_indexer = FakeIndexer()
    monkeypatch.setattr(harvester_module, "OpacClient", FakeOpacClient)
    monkeypatch.setattr(harvester_module, "Harvester", FakeHarvester)
    monkeypatch.setattr(indexer_module, "MeiliIndexer", lambda: fake_indexer)

    processed, backoff = worker_tick(session)
    session.commit()

    assert processed is not None
    assert processed.status == "completed"
    assert fake_indexer.calls == [["1", "2"]]
    assert backoff == 0.0


def test_titn_pendientes_de_indexar_se_reintentan(monkeypatch) -> None:
    import mediateca.catalog.harvester as harvester_module
    import mediateca.catalog.indexer as indexer_module

    session = _session()
    create_job(session, "enrich", batch_size=10, max_attempts=2)
    session.commit()

    class FakeOpacClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

    class FakeHarvester:
        def __init__(self, session, client) -> None:
            pass

        def harvest_enrichment(self, *, job):  # noqa: ANN001
            return {"processed": 2, "processed_titns": ["1", "2"]}

    class FakeIndexer:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []
            self.attempts = 0

        def index_titns(self, session, titns):  # noqa: ANN001
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("meilisearch no disponible")
            self.calls.append(list(titns))
            return len(titns)

    fake_indexer = FakeIndexer()
    monkeypatch.setattr(harvester_module, "OpacClient", FakeOpacClient)
    monkeypatch.setattr(harvester_module, "Harvester", FakeHarvester)
    monkeypatch.setattr(indexer_module, "MeiliIndexer", lambda: fake_indexer)

    first, backoff = worker_tick(session)
    session.commit()

    assert first is not None
    assert first.status == "pending"
    assert first.attempts == 1
    assert first.stats["pending_index_titns"] == ["1", "2"]
    assert backoff > 0

    second, backoff = worker_tick(session)
    session.commit()

    assert second is not None
    assert second.status == "completed"
    assert second.attempts == 2
    assert "pending_index_titns" not in second.stats
    assert fake_indexer.calls[0] == ["1", "2"]
    assert backoff == 0.0


def test_worker_usa_la_url_de_flaresolverr_persistida(monkeypatch) -> None:
    import mediateca.catalog.harvester as harvester_module
    from mediateca.core.config_store import FLARESOLVERR_URL_KEY, set_config_value

    session = _session()
    set_config_value(session, FLARESOLVERR_URL_KEY, "http://db:8191")
    create_job(session, "discover")
    session.commit()

    capturado: dict = {}

    class FakeOpacClient:
        def __init__(self, *args, **kwargs) -> None:
            capturado.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

    class FakeHarvester:
        def __init__(self, session, client) -> None:
            pass

        def harvest_discovery(self, *, job):  # noqa: ANN001
            return {"processed": 0}

    monkeypatch.setattr(harvester_module, "OpacClient", FakeOpacClient)
    monkeypatch.setattr(harvester_module, "Harvester", FakeHarvester)

    processed, backoff = worker_tick(session)
    session.commit()

    assert processed is not None
    assert processed.status == "completed"
    assert capturado["flaresolverr_url"] == "http://db:8191"
    assert backoff == 0.0


def test_recupera_trabajo_estancado_y_lo_reencola() -> None:
    session = _session()
    start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    job = create_job(session, "enrich", max_attempts=3)
    claimed = claim_job(session, now=start)
    session.commit()

    recuperados = recover_stale_jobs(
        session, now=start + timedelta(minutes=5), stale_seconds=120
    )
    session.commit()

    assert recuperados == 1
    assert claimed is not None
    assert job.status == "pending"
    assert job.started_at is None
    assert job.error == "Heartbeat caducado; trabajo reencolado"


def test_trabajo_estancado_sin_intentos_termina_failed() -> None:
    session = _session()
    start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    job = create_job(session, "enrich", max_attempts=1)
    claim_job(session, now=start)
    session.commit()

    recuperados = recover_stale_jobs(
        session, now=start + timedelta(minutes=5), stale_seconds=120
    )
    session.commit()

    assert recuperados == 1
    assert job.status == "failed"
    assert job.error == "Heartbeat caducado; se agotaron los intentos"


def test_worker_tick_recupera_y_reclama_el_trabajo_estancado() -> None:
    session = _session()
    start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    job = create_job(session, "enrich", max_attempts=3)
    claim_job(session, now=start)
    session.commit()

    processed, backoff = worker_tick(
        session,
        handlers={"enrich": lambda session, job: {"processed": 0}},
    )
    session.commit()

    assert processed is not None
    assert processed.id == job.id
    assert processed.status == "completed"
    assert processed.attempts == 2
    assert backoff == 0.0


def test_descubrimiento_con_nuevos_encola_enriquecimiento(monkeypatch) -> None:
    import mediateca.catalog.harvester as harvester_module

    session = _session()
    create_job(session, "discover")
    session.commit()

    class FakeOpacClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

    class FakeHarvester:
        def __init__(self, session, client) -> None:
            self.session = session

        def harvest_discovery(self, *, job):  # noqa: ANN001
            create_stub(self.session, "100")
            return {"processed": 1}

    monkeypatch.setattr(harvester_module, "OpacClient", FakeOpacClient)
    monkeypatch.setattr(harvester_module, "Harvester", FakeHarvester)

    processed, _ = worker_tick(session)
    session.commit()

    assert processed is not None
    assert processed.job_type == "discover"
    enrich = session.scalars(
        select(HarvestJob).where(HarvestJob.job_type == "enrich")
    ).first()
    assert enrich is not None
    assert enrich.status == "pending"
    assert "since" in enrich.stats
    assert enrich.stats["reason"] == "after_discover"


def test_indexa_los_titn_procesados_si_el_lote_falla(monkeypatch) -> None:
    import mediateca.catalog.harvester as harvester_module
    import mediateca.catalog.indexer as indexer_module

    session = _session()
    job = create_job(session, "enrich", batch_size=10)
    session.commit()

    class FakeOpacClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

    class FakeHarvester:
        processed_titns = ["1", "2"]

        def __init__(self, session, client) -> None:
            pass

        def harvest_enrichment(self, *, job):  # noqa: ANN001
            raise RuntimeError("captcha")

    class FakeIndexer:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def index_titns(self, session, titns):  # noqa: ANN001
            self.calls.append(list(titns))
            return len(titns)

    fake_indexer = FakeIndexer()
    monkeypatch.setattr(harvester_module, "OpacClient", FakeOpacClient)
    monkeypatch.setattr(harvester_module, "Harvester", FakeHarvester)
    monkeypatch.setattr(indexer_module, "MeiliIndexer", lambda: fake_indexer)

    with pytest.raises(RuntimeError):
        _enrich_handler(session, job)

    assert fake_indexer.calls == [["1", "2"]]


def test_captcha_reencola_y_pausa_la_ingesta() -> None:
    session = _session()
    create_job(session, "enrich")
    save_schedule_settings(
        session,
        ScheduleSettings(
            True,
            12,
            168,
            12,
            5000,
            index_interval_hours=168,
            captcha_pause_minutes=15,
        ),
    )
    session.commit()

    def handler(session, job):  # noqa: ANN001, ANN202
        raise CaptchaRequired("captcha")

    processed, backoff = worker_tick(session, handlers={"enrich": handler})
    session.commit()

    assert processed is not None
    assert processed.status == "pending"
    assert processed.attempts == 0
    assert processed.error == "captcha"
    assert backoff == 900.0
