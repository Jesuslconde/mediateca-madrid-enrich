# Proposal

## Why

La ingesta completa del catálogo de vídeo requiere trabajos de varias horas que deben poder reanudarse tras un fallo, un reinicio del contenedor o una sesión caducada. Hoy `HarvestRun` solo guarda estadísticas y no existe un estado persistente por edición que permita saber qué se ha descubierto, qué se ha enriquecido y qué falta.

## What Changes

- Añadir una tabla de trabajos de ingesta con tipo, estado, cursor, reintentos y estadísticas.
- Añadir marcas de progreso por edición: `discovery_seen_at`, `detail_fetched_at` y `is_stub`.
- Permitir que descubrimiento y enriquecimiento se reanuden desde un cursor (`cursor_doc`, `cursor_titn`).
- Definir la idempotencia de las actualizaciones por `TITN`.
- Exponer el estado de los trabajos y la cobertura desde CLI y API.
- Añadir un script SQL idempotente para bases de datos existentes, ya que `create_all` no añade columnas.

## Capabilities

### New Capabilities

- `estado-ingesta`: modelo persistente de trabajos, cursores y marcas de progreso de la ingesta masiva.

### Modified Capabilities

Ninguna.

## Impact

- `backend/src/mediateca/catalog/models.py`: nuevas tablas y columnas.
- `backend/src/mediateca/core/db.py`: inicialización y migración.
- `backend/src/mediateca/catalog/repository.py`: helpers de estado y cursores.
- `backend/src/mediateca/cli.py`: comandos de consulta de estado.
- `scripts/migrate_ingesta.sql`: migración idempotente.
- Tests de modelos y repositorio.
