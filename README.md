# Mediateca Madrid - enrich

Proyecto de ingesta, descubrimiento, enriquecimiento, worker, scheduler e indexacion del catalogo de Mediateca Madrid. Escribe en PostgreSQL y Meilisearch; la API y el portal solo leen de esos almacenamientos.

## Arranque

```bash
cp .env.example .env 2>/dev/null || true
make up
make migrate
make init
```

El worker procesa `harvest_jobs`; el scheduler solo planifica. La API y el portal se despliegan desde `mediateca-madrid`.

## Comandos

```bash
make help
make harvest q=cine pages=2 limit=20
make index
make worker-logs
make dashboard
make dashboard-logs
make test
make lint
make psql
```

El enriquecimiento completo se ejecuta en lotes de 5.000 fichas:

```bash
docker compose run --rm worker mediateca enrich --limit 5000
```

A 1 peticion por segundo cada lote tarda aproximadamente 1,4 horas. El trabajo
guarda un cursor por `TITN`, reintenta las fichas fallidas y solo persiste datos
parseados: no crea snapshots HTML ni escribe en `MEDIATECA_RAW_DIR`.

## Dashboard de estado

La vista web muestra en modo de solo lectura los trabajos por estado y tipo, los
trabajos recientes, la cobertura del catalogo y la salud del worker. No crea,
modifica ni elimina datos, no encola trabajos y no toca el indice.

```bash
make dashboard        # Levanta el servicio dashboard en segundo plano
make dashboard-logs   # Sigue los logs del servicio
```

Queda disponible en `http://localhost:8080`. En local tambien se puede arrancar
con el comando de la CLI:

```bash
mediateca dashboard --host 127.0.0.1 --port 8080
```

La misma aplicacion expone la API de observabilidad de solo lectura:

```bash
curl http://localhost:8080/api/ingest/status
curl http://localhost:8080/api/ingest/coverage
```

Tambien se puede consultar desde la CLI:

```bash
docker compose run --rm worker mediateca ingest-status
```

Variables de configuracion:

- `MEDIATECA_DASHBOARD_HOST` y `MEDIATECA_DASHBOARD_PORT`: host y puerto de escucha.
- `MEDIATECA_DASHBOARD_REFRESH_SECONDS`: intervalo de refresco automatico de la pagina.
- `MEDIATECA_DASHBOARD_RECENT_LIMIT`: numero de trabajos recientes mostrados.
- `MEDIATECA_DASHBOARD_WORKER_STALE_SECONDS`: antiguedad maxima del heartbeat antes
  de marcar el worker como `degraded`.

## Migraciones

- `scripts/migrate_disponibilidad.sql`: retirada del estado de prestamo.
- `scripts/migrate_ingesta.sql`: `harvest_jobs`, marcas de progreso, `schema_meta`
  y retirada idempotente de la tabla `snapshots`.

Ambas son idempotentes. `make migrate` requiere PostgreSQL levantado.

## OpenSpec

La planificacion de ingesta vive en este repositorio. Los cambios `estado-ingesta`, `cola-worker`, `descubrimiento-catalogo`, `enriquecimiento-fichas`, `indexacion-incremental` y `observabilidad-ingesta` se migraron desde `mediateca-madrid`.
