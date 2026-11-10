# Tasks

## 1. Encolado y configuración

- [x] 1.1 Implementar `enqueue_job`, deduplicación por tipo y helpers de descubrimiento, enriquecimiento e indexación en `catalog/jobs.py`
- [x] 1.2 Añadir `core/scheduling.py` con configuración, validación, última y próxima ejecución
- [x] 1.3 Añadir descubrimiento incremental por cursor y filtro `since` en repositorio y harvester
- [x] 1.4 Encadenar automáticamente `enrich` tras un descubrimiento con nuevos registros
- [x] 1.5 Añadir tests de encolado, deduplicación, cursor incremental, filtro `since` y programación

## 2. Scheduler y despliegue

- [x] 2.1 Implementar `catalog/scheduler.py` con cálculo de trabajos debidos y bucle de comprobación
- [x] 2.2 Cambiar `mediateca scheduler` para encolar y añadir modo `--once`
- [x] 2.3 Añadir el servicio `scheduler` a `docker-compose.yml` y al stack de Portainer
- [x] 2.4 Añadir variables de configuración del scheduler y token del dashboard a `.env.example`

## 3. Dashboard

- [x] 3.1 Añadir configuración de programación y estado de última/próxima ejecución
- [x] 3.2 Añadir tareas bajo demanda para descubrir, enriquecer e indexar
- [x] 3.3 Añadir token de escritura, login/logout y cookie segura
- [x] 3.4 Añadir tests de endpoints, validación, deduplicación y autenticación

## 4. Verificación y documentación

- [x] 4.1 Actualizar `README.md` y `docs/ARCHITECTURE.md`
- [x] 4.2 Ejecutar `pytest -q` y `ruff check src tests`
- [x] 4.3 Recompilar y publicar la imagen, actualizar el stack y verificar scheduler, worker, dashboard y primer trabajo programado
