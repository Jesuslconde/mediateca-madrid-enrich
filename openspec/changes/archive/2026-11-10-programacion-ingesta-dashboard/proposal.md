# Proposal

## Why

La cola `harvest_jobs` existía, pero no había ningún productor desplegado: el scheduler no encolaba, el dashboard no permitía lanzar tareas y los nuevos registros no se descubrían ni enriquecían de forma periódica. La ingesta quedaba parada tras el primer fallo.

## What Changes

- Añadir encolado de trabajos desde el dashboard y desde el scheduler, con deduplicación por tipo activo.
- Añadir tareas bajo demanda desde el dashboard: descubrimiento incremental, descubrimiento completo, enriquecimiento e indexación.
- Añadir programación configurable desde el dashboard: activación, intervalo de descubrimiento, barrido completo, intervalo de enriquecimiento y tamaño de lote.
- Implementar descubrimiento incremental reutilizando el cursor del último descubrimiento completado, con barrido completo semanal de seguridad.
- Enriquecer solo los registros nuevos descubiertos en la última pasada mediante un filtro `since`.
- Encadenar automáticamente el enriquecimiento al finalizar un descubrimiento con nuevos registros.
- Añadir el servicio `scheduler` al despliegue y un token de escritura para el dashboard.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `dashboard-ingesta`: permite encolar trabajos y editar la programación, con token de escritura.
- `cola-trabajos`: añade encolado desde dashboard/scheduler, deduplicación y ejecución programada.
- `ingesta-catalogo`: añade descubrimiento incremental por cursor y enriquecimiento de nuevos registros.
- `operacion-despliegue`: añade el servicio `scheduler` y el token de administración del dashboard.

## Impact

- `src/mediateca/catalog/jobs.py`: encolado, deduplicación y encadenado discover → enrich.
- `src/mediateca/catalog/scheduler.py` (nuevo): cálculo de trabajos programados y bucle del scheduler.
- `src/mediateca/core/scheduling.py` (nuevo): configuración, validación y estado de la programación.
- `src/mediateca/catalog/harvester.py` y `repository.py`: cursor incremental y filtro `since`.
- `src/mediateca/dashboard/`: endpoints, formularios, token y estado de programación.
- `src/mediateca/cli.py`: `mediateca scheduler` pasa a encolar.
- `docker-compose.yml` y `portainer-stack.yml`: servicio `scheduler` y variables nuevas.
- Tests, `README.md` y `docs/ARCHITECTURE.md`.
