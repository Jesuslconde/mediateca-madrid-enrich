# Design

## Context

El proyecto usa SQLAlchemy con `Base.metadata.create_all` y no tiene Alembic. La ingesta actual guarda `HarvestRun` con estadísticas, pero no un cursor ni marcas por edición. Una ingesta completa de 67.215 fichas puede durar horas y debe sobrevivir a reinicios.

## Goals / Non-Goals

**Goals:**

- Persistir trabajos, cursores y marcas de progreso.
- Permitir reanudación exacta y actualizaciones idempotentes.
- Añadir el esquema a bases existentes sin perder datos.

**Non-Goals:**

- Introducir Alembic u otro framework de migraciones completo.
- Implementar la cola o el worker; eso corresponde al cambio `cola-worker`.
- Cambiar el modelo obra/edición/ejemplar.

## Decisions

### 1. Tabla `harvest_jobs`

Campos: `id`, `job_type` (`discover`, `enrich`, `index`), `status` (`pending`, `running`, `completed`, `failed`, `cancelled`), `cursor_doc`, `cursor_titn`, `batch_size`, `attempts`, `max_attempts`, `stats` JSONB, `error`, `created_at`, `started_at`, `finished_at`, `heartbeat_at`.

- **Por qué**: permite reanudar y observar trabajos largos sin una cola externa.
- **Alternativa descartada**: usar solo `HarvestRun`; no tiene cursor ni heartbeat.

### 2. Campos en `ediciones`

`is_stub` (booleano), `discovery_seen_at`, `detail_fetched_at`, `missing_at`.

- **Por qué**: el descubrimiento crea stubs y el enriquecimiento los completa; la disponibilidad se elimina en `simplificar-disponibilidad-bibliotecas`.
- **Alternativa descartada**: una tabla auxiliar por cada marca; añade joins sin beneficio.

### 3. Migración idempotente en SQL

Se añade `scripts/migrate_ingesta.sql` con `CREATE TABLE IF NOT EXISTS` y `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, más un objetivo `make migrate-ingesta`.

- **Por qué**: `create_all` no modifica tablas existentes y el proyecto no usa Alembic.
- **Alternativa descartada**: Alembic; se pospone hasta que el esquema se estabilice.

### 4. Índices

Índices en `harvest_jobs(status, job_type)`, `ediciones(is_stub)`, `ediciones(detail_fetched_at)` y `ediciones(discovery_seen_at)`.

- **Por qué**: las consultas de selección de lotes deben ser rápidas con 67k ediciones.

## Risks / Trade-offs

- [Migración manual] → Script idempotente, probado dos veces seguidas.
- [Crecimiento de `harvest_jobs`] → Retención de trabajos antiguos y archivado.
- [Cursores desactualizados si cambia el catálogo] → Verificar el primer `TITN` de la página y reiniciar el tramo si no coincide.
- [Campos nuevos en tablas grandes] → Añadir columnas nullable y crear índices después.

## Migration Plan

1. Ejecutar `make migrate-ingesta` sobre PostgreSQL.
2. Ejecutar `mediateca init-db` para crear tablas nuevas si faltan.
3. Verificar que las columnas y tablas existen.
4. Rollback: las columnas nullable pueden quedarse; no se eliminan datos existentes.
