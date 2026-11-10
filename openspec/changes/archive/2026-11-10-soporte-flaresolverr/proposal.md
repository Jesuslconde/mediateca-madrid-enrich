# Proposal

## Why

El OPAC responde con un reCAPTCHA cuando detecta automatización y la ingesta se detiene, dejando lotes de descubrimiento y enriquecimiento incompletos durante horas. Hoy el recolector no puede continuar porque la especificación vigente prohíbe eludir el captcha.

## What Changes

- Detectar el reCAPTCHA como hasta ahora y, solo cuando exista una URL de FlareSolverr configurada, reintentar la misma petición a través de FlareSolverr y continuar con la respuesta resuelta.
- Mantener `httpx` como transporte normal: FlareSolverr es un fallback ante captcha, no el canal principal.
- Añadir configuración editable desde el dashboard para la URL de FlareSolverr, persistida en PostgreSQL y con la variable de entorno como valor por defecto.
- Sincronizar las cookies devueltas por FlareSolverr con la sesión del OPAC para no perder el contexto de búsqueda ni la paginación.
- Registrar métricas de captchas detectados, resueltos y fallidos en las estadísticas de los trabajos y en la observabilidad.
- **BREAKING**: se modifica la política vigente que prohíbe eludir mecanismos de protección. La recolección seguirá deteniéndose si no hay FlareSolverr configurado o si la resolución falla.
- **BREAKING**: el dashboard deja de ser estrictamente de solo lectura; solo la configuración de FlareSolverr puede escribir en la base de datos y el resto de la vista sigue siendo de lectura.
- No se añade un servicio FlareSolverr al `docker-compose.yml`; el operador apunta `MEDIATECA_FLARESOLVERR_URL` a una instancia propia o lo configura desde el dashboard.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `ingesta-catalogo`: se sustituye la prohibición de eludir reCAPTCHA por una resolución opcional vía FlareSolverr y se documenta la sincronización de cookies y la política de fallo.
- `dashboard-ingesta`: se permite una única escritura de configuración para la URL de FlareSolverr y se añade su sección editable con estado de configuración.
- `observabilidad-ingesta`: se amplían las métricas de captcha con los contadores de resueltos y fallidos.

## Impact

- `src/mediateca/catalog/harvester.py`: integración del fallback y sincronización de cookies.
- `src/mediateca/catalog/flaresolverr.py` (nuevo): cliente HTTP de la API de FlareSolverr.
- `src/mediateca/core/config.py`: nueva variable `MEDIATECA_FLARESOLVERR_URL` y timeout.
- `src/mediateca/core/` (nuevo almacén de configuración): modelo y lectura/escritura de la URL efectiva.
- `src/mediateca/dashboard/app.py`, `queries.py` y `templates/dashboard.html`: sección editable y ruta de actualización.
- `src/mediateca/catalog/jobs.py`, `src/mediateca/cli.py` y `src/mediateca/api/routers/ingest.py`: resolución de la configuración y nuevas métricas.
- `scripts/` y `Makefile`: migración idempotente para la tabla de configuración.
- `tests/`: cliente FlareSolverr, fallback, configuración del dashboard y métricas.
- `docs/ARCHITECTURE.md` y `README.md`: comportamiento, configuración y riesgos operativos.
- Dependencias externas: instancia de FlareSolverr accesible por HTTP; sin nuevas librerías Python.
