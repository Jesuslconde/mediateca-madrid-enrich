# Tasks

## 1. Dependencias y configuración

- [x] 1.1 Añadir `fastapi`, `uvicorn` y `jinja2` a `pyproject.toml`, y verificar que `pip install -e ".[dev]"` termina sin errores y que `python -c "import fastapi, uvicorn, jinja2"` funciona
- [x] 1.2 Añadir `dashboard_host`, `dashboard_port`, `dashboard_refresh_seconds`, `dashboard_recent_limit` y `dashboard_worker_stale_seconds` a `core/config.py`, y verificar con un test que los valores por defecto y las variables `MEDIATECA_DASHBOARD_*` se cargan
- [x] 1.3 Documentar las variables `MEDIATECA_DASHBOARD_*` en `.env.example` y verificar que los nombres coinciden con los campos de `Settings`

## 2. Consultas de solo lectura

- [x] 2.1 Implementar `job_status_counts()`, `job_type_counts()` y `recent_jobs()` en `dashboard/queries.py`, reutilizando `coverage()`, y verificar con tests sobre SQLite que devuelven los conteos y el orden esperados
- [x] 2.2 Implementar `worker_health()` con el fichero de heartbeat como fuente principal y el `heartbeat_at` de la base de datos como respaldo, y verificar con tests los estados `ok` y `degraded`
- [x] 2.3 Cubrir los casos límite de catálogo vacío y división por cero en el porcentaje de enriquecimiento, y verificar que los tests devuelven cero sin excepción

## 3. Aplicación web

- [x] 3.1 Crear `dashboard/app.py` con `GET /` renderizando `templates/dashboard.html` y `GET /health` devolviendo JSON, y verificar con `TestClient` que ambas rutas responden `200`
- [x] 3.2 Mostrar en la plantilla el resumen por estado y tipo, el detalle de trabajos recientes, la cobertura y la salud del worker, y verificar con un test que el HTML contiene los valores de datos de prueba
- [x] 3.3 Añadir `templates/degraded.html` y capturar `SQLAlchemyError`, y verificar con un test que una base de datos no disponible devuelve el mensaje degradado sin trazas internas
- [x] 3.4 Añadir el refresco automático mediante `<meta http-equiv="refresh">` con el intervalo configurado, y verificar con un test que el HTML incluye el intervalo esperado
- [x] 3.5 Verificar que la vista es de solo lectura con un test que comprueba que varias peticiones no alteran los conteos de trabajos ni de ediciones

## 4. CLI y ejecución local

- [x] 4.1 Añadir el comando `mediateca dashboard` que arranca Uvicorn con host, puerto e intervalo de configuración, y verificar con `CliRunner` que el comando aparece en `mediateca --help`
- [x] 4.2 Verificar el arranque local con `mediateca dashboard` y una petición de humo a `http://127.0.0.1:8080/health` que devuelve `200`

## 5. Despliegue y documentación

- [x] 5.1 Añadir el servicio `dashboard` a `docker-compose.yml` con la misma imagen, puerto configurable, dependencia de `db` y healthcheck a `/health`, y verificar con `docker compose config`
- [x] 5.2 Añadir los objetivos `dashboard` y `dashboard-logs` al `Makefile`, y verificar que `make help` los muestra
- [x] 5.3 Documentar en `README.md` el arranque, la URL, las variables de configuración y el carácter de solo lectura de la vista, y verificar que los comandos documentados se ejecutan tal cual

## 6. Verificación de integración

- [x] 6.1 Ejecutar `pytest -q` y verificar que toda la suite pasa, incluidos los tests nuevos del dashboard
- [x] 6.2 Ejecutar `ruff check src tests` y verificar que no hay fallos
