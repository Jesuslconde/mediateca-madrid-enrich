# Proposal

## Why

La cola de ingesta ya persiste los trabajos en `harvest_jobs`, pero para conocer su estado hay que ejecutar `mediateca status` o consultar PostgreSQL directamente. Falta una vista web pequeña y de solo lectura que permita al operador ver de un vistazo qué tareas están pendientes, en ejecución, completadas o fallidas, y cómo avanza la cobertura del catálogo.

## What Changes

- Añadir una vista web de solo lectura para el estado de los trabajos de ingesta (`harvest_jobs`).
- Mostrar un resumen de trabajos por estado (`pending`, `running`, `completed`, `failed`, `cancelled`) y por tipo (`discover`, `enrich`, `index`).
- Listar los trabajos recientes con identificador, tipo, estado, cursor, intentos, fechas, heartbeat y error.
- Mostrar la cobertura del catálogo: descubiertas, enriquecidas, pendientes y fallidas.
- Mostrar la salud del worker a partir de su heartbeat.
- Refrescar la página automáticamente con un intervalo configurable.
- Servir la vista mediante el comando `mediateca dashboard` y un servicio `dashboard` en Docker Compose.
- La vista es estrictamente de lectura: no modifica datos, no encola ni ejecuta trabajos.

## Capabilities

### New Capabilities

- `dashboard-ingesta`: vista web de solo lectura con resumen, detalle, cobertura y salud del worker para los trabajos de ingesta.

### Modified Capabilities

- `operacion-despliegue`: se añade el servicio `dashboard` al despliegue Docker, con puerto configurable y healthcheck.

## Impact

- `src/mediateca/dashboard/` (nuevo módulo: aplicación web, plantilla y consultas de solo lectura).
- `src/mediateca/cli.py`: comando `dashboard`.
- `src/mediateca/core/config.py`: host, puerto e intervalo de refresco del dashboard.
- `pyproject.toml`: dependencias `fastapi`, `uvicorn` y `jinja2`.
- `docker-compose.yml`: servicio `dashboard` con el mismo build que el worker.
- `.env.example`, `Makefile` y `README.md`.
- Tests de las consultas del dashboard y de la respuesta de la vista.
