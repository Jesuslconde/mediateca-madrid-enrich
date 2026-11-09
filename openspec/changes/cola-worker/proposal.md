# Proposal

## Why

Los trabajos de descubrimiento y enriquecimiento pueden durar horas. Ejecutarlos dentro de APScheduler bloquea el scheduler, complica la reanudación y mezcla responsabilidades. Se necesita una cola persistente y un worker que ejecute un trabajo cada vez, con reintentos y estado visible.

## What Changes

- Añadir una cola de trabajos respaldada por PostgreSQL usando la tabla `harvest_jobs`.
- Añadir un servicio `worker` que reclame trabajos con `FOR UPDATE SKIP LOCKED` y los ejecute de uno en uno.
- Mantener el scheduler como planificador: solo encola trabajos, no ejecuta ingestas largas.
- Definir reintentos, backoff, heartbeat, cancelación y estados finales.
- Añadir el servicio `worker` a Docker Compose usando la misma imagen del backend.
- **No** se crea un proyecto separado para la ingesta: se mantiene el monorepo.

## Capabilities

### New Capabilities

- `cola-trabajos`: cola persistente, reclamación atómica, ejecución por worker, reintentos y bloqueo.

### Modified Capabilities

- `operacion-despliegue`: se añade el servicio `worker` al despliegue Docker y su healthcheck.

## Impact

- `backend/src/mediateca/catalog/models.py`: `HarvestJob` (depende de `estado-ingesta`).
- `backend/src/mediateca/catalog/jobs.py`: encolado, reclamo, heartbeat y finalización.
- `backend/src/mediateca/cli.py`: comando `worker` y utilidades de cola.
- `docker-compose.yml`: servicio `worker` con la misma imagen `mediateca-backend:local`.
- `Makefile`, `README.md` y `docs/ARCHITECTURE.md`.
- Tests de cola y worker.
