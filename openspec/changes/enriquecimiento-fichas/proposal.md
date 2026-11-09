# Proposal

## Why

El descubrimiento deja 67.215 TITN en forma de stub. Para que el portal tenga créditos, sinopsis, materias y ejemplares hay que descargar la ficha completa de cada uno. El usuario ha decidido enriquecer todo, en lotes de 5.000, y guardar solo datos parseados, sin snapshots HTML.

## What Changes

- Añadir el trabajo de enriquecimiento completo por lotes de 5.000 TITN.
- Seleccionar stubs con `detail_fetched_at IS NULL` o marcados como obsoletos.
- Descargar cada ficha por `TITN`, parsear metadatos completos y ejemplares, y actualizar la edición.
- **BREAKING** Dejar de persistir HTML crudo: se elimina el guardado de snapshots y la tabla `snapshots`.
- Guardar `detail_fetched_at` y el cursor `cursor_titn` para reanudar.
- Reintentar fichas fallidas con backoff y registrar el error.
- Indexar el lote al terminar (depende de `indexacion-incremental`).
- Ejecutar por defecto a 1 req/s: 5.000 fichas ≈ 1,4 h por lote.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `ingesta-catalogo`: se añade el enriquecimiento por lotes y se elimina la persistencia de snapshots.

## Impact

- `backend/src/mediateca/catalog/harvester.py`: enriquecimiento por lotes y eliminación del guardado de snapshots.
- `backend/src/mediateca/catalog/models.py`: eliminar `Snapshot` y su relación.
- `backend/src/mediateca/catalog/repository.py`: eliminar `save_snapshot`; añadir selección de stubs y marcas de progreso.
- `backend/src/mediateca/cli.py`: comando `enrich`.
- `backend/src/mediateca/catalog/jobs.py`: tipo `enrich`.
- `scripts/migrate_ingesta.sql` o migración específica para eliminar `snapshots`.
- Tests de enriquecimiento, idempotencia y ausencia de snapshots.
