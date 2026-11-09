# Tasks

## 1. Cola y worker

- [x] 1.1 Implementar `backend/src/mediateca/catalog/jobs.py` con encolar, reclamar con `FOR UPDATE SKIP LOCKED`, heartbeat y finalizar, y verificar con tests que dos reclamos simultáneos no obtienen el mismo trabajo
- [x] 1.2 Añadir el comando `mediateca worker` con bucle de reclamo, ejecución y backoff, y verificar que procesa un trabajo de prueba
- [x] 1.3 Configurar `MEDIATECA_WORKER_CONCURRENCY`, `MEDIATECA_WORKER_POLL_SECONDS` y `MEDIATECA_WORKER_HEARTBEAT_SECONDS` en `core/config.py` y `.env.example`

## 2. Docker y operación

- [x] 2.1 Añadir el servicio `worker` a `docker-compose.yml` con la misma imagen del backend, variables de entorno y volumen de datos, y verificar con `docker compose config`
- [x] 2.2 Añadir healthcheck o heartbeat verificable del worker y verificar que Docker lo marca unhealthy al detenerlo
- [x] 2.3 Actualizar `Makefile` con `make worker-logs` y `make worker-shell`, y verificar `make help`

## 3. Pruebas y documentación

- [x] 3.1 Añadir tests de cola, reintentos y heartbeat, y verificar con `pytest -q`
- [x] 3.2 Documentar el flujo scheduler → cola → worker en `docs/ARCHITECTURE.md` y `README.md`
- [x] 3.3 Ejecutar `ruff check src tests` y verificar que no hay fallos
