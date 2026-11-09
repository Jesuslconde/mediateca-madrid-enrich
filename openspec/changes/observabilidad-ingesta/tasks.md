# Tasks

## 1. Consultas y API

- [ ] 1.1 Implementar consultas de trabajos y cobertura en `catalog/jobs.py` o `catalog/repository.py`, y verificar con datos de prueba
- [ ] 1.2 Añadir `GET /api/ingest/status` y `GET /api/ingest/coverage`, y verificar con una petición de humo
- [ ] 1.3 Añadir schemas Pydantic para las respuestas y verificar que `/docs` las muestra

## 2. CLI y logs

- [ ] 2.1 Añadir `mediateca ingest-status` y verificar la tabla de trabajos y cobertura
- [ ] 2.2 Configurar logs JSON con `job_id`, `job_type`, `titn`, `result` y `duration_ms` en los jobs de ingesta
- [ ] 2.3 Añadir el heartbeat del worker al estado y verificar que un worker detenido marca `degraded`

## 3. Pruebas y documentación

- [ ] 3.1 Añadir tests de cobertura y de health del worker, y verificar con `pytest -q`
- [ ] 3.2 Documentar los endpoints, el CLI y las métricas en `docs/ARCHITECTURE.md` y `README.md`
- [ ] 3.3 Ejecutar `ruff check src tests` y verificar que no hay fallos
