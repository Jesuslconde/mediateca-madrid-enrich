# Design

## Context

Ver `proposal.md`. `harvest_jobs` y las marcas por edición se introducen en `estado-ingesta`. El worker y la cola se introducen en `cola-worker`.

## Goals / Non-Goals

**Goals:**

- Saber qué se ha procesado, qué falta y qué falla.
- Detectar worker caído o ingesta estancada.
- Tener logs útiles sin datos personales.

**Non-Goals:**

- Montar Prometheus/Grafana en el MVP.
- Trazas distribuidas.
- Alertas por email/Slack.

## Decisions

### 1. API `/api/ingest/status` y `/api/ingest/coverage`

Devuelven trabajos recientes, cobertura y heartbeat. Se leen de PostgreSQL, sin llamar al OPAC.

- **Por qué**: el estado debe funcionar aunque el OPAC esté caído.
- **Alternativa descartada**: consultar el OPAC para el estado; no aporta.

### 2. CLI `mediateca ingest-status`

Muestra una tabla con trabajos y cobertura, reutilizando las mismas consultas que la API.

- **Por qué**: comodidad para operación por SSH o dentro del contenedor.

### 3. Logs estructurados con `logging` JSON

Se configura un formatter JSON para los jobs de ingesta. Campos: `timestamp`, `level`, `logger`, `job_id`, `job_type`, `titn`, `doc`, `result`, `duration_ms`, `error`.

- **Por qué**: facilita búsquedas y agregación sin añadir dependencias.

### 4. Métricas en base de datos, no Prometheus

Contadores en `harvest_jobs.stats` y en una tabla `ingest_metrics` si se necesita histórico. Para el MVP, `stats` es suficiente.

- **Por qué**: evitar infraestructura extra.
- **Alternativa descartada**: Prometheus; se puede añadir después.

### 5. Salud del worker

El worker actualiza `heartbeat_at`. La API considera degradada la ingesta si el último heartbeat tiene más de `MEDIATECA_WORKER_HEARTBEAT_TIMEOUT`.

## Risks / Trade-offs

- [Crecimiento de métricas] → Agregar por job y retener N días.
- [Logs verbosos] → Nivel configurable y muestreo de fichas correctas.
- [Estado desactualizado] → Heartbeat y timestamps.
- [Confusión con `/health`] → `/health` es infraestructura; `/api/ingest/status` es ingesta.

## Migration Plan

1. Implementar consultas de estado y cobertura.
2. Exponer endpoints y CLI.
3. Configurar logs JSON en los jobs.
4. Verificar con un trabajo de prueba.
5. Rollback: los endpoints son de solo lectura y no afectan a la ingesta.
