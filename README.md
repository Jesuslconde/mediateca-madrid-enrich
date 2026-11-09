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

## Migraciones

- `scripts/migrate_disponibilidad.sql`: retirada del estado de prestamo.
- `scripts/migrate_ingesta.sql`: `harvest_jobs`, marcas de progreso, `schema_meta`
  y retirada idempotente de la tabla `snapshots`.

Ambas son idempotentes. `make migrate` requiere PostgreSQL levantado.

## OpenSpec

La planificacion de ingesta vive en este repositorio. Los cambios `estado-ingesta`, `cola-worker`, `descubrimiento-catalogo`, `enriquecimiento-fichas`, `indexacion-incremental` y `observabilidad-ingesta` se migraron desde `mediateca-madrid`.
