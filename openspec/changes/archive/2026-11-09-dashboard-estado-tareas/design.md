# Design

## Context

Ver `proposal.md` - Why. El repositorio es un paquete Python 3.11+ con SQLAlchemy 2, PostgreSQL y una CLI basada en Typer/Rich. No hay servidor web propio: la API y el portal viven en el repositorio `mediateca-madrid`. La tabla `harvest_jobs` y el modelo `HarvestJob` ya existen en `mediateca_shared.models`, y `catalog/jobs.py` ofrece `coverage()` con los conteos de trabajos y ediciones. El worker escribe un fichero de heartbeat configurable en `MEDIATECA_WORKER_HEARTBEAT_FILE`.

## Goals / Non-Goals

**Goals:**

- Servir una vista web pequeña de solo lectura sin acoplarla al portal.
- Reutilizar el modelo y las consultas existentes de trabajos y cobertura.
- Poder ejecutarse en local y como servicio de Docker Compose.
- Ser testeable sin PostgreSQL real.

**Non-Goals:**

- Encender, cancelar o reintentar trabajos desde la vista.
- Autenticación, multiusuario o control de acceso por roles.
- Actualizaciones en tiempo real por WebSocket.
- Sustituir el comando `mediateca status`.
- Cambiar el modelo `HarvestJob` o el esquema de la base de datos.

## Decisions

### 1. FastAPI + Uvicorn + Jinja2

Se sirve la vista con FastAPI y Uvicorn, renderizando una plantilla Jinja2 en el servidor.

- **Por qué**: es un servidor ASGI mínimo, tipado y ya habitual en el ecosistema; permite tests con `TestClient` sin levantar un puerto.
- **Alternativa descartada**: `http.server` de la biblioteca estándar; obliga a construir a mano el enrutado, las plantillas y los tests. Una SPA con build de frontend añade complejidad desproporcionada para una sola página.

### 2. Módulo `mediateca.dashboard` de solo lectura

Se crea `src/mediateca/dashboard/` con `app.py` (rutas), `queries.py` (agregaciones de lectura), `templates/dashboard.html` y `templates/degraded.html`. `queries.py` reutiliza `coverage()` de `catalog/jobs.py` y añade `job_status_counts()`, `job_type_counts()`, `recent_jobs()` y `worker_health()`.

- **Por qué**: separa la vista de la lógica de ingesta y evita duplicar consultas.
- **Alternativa descartada**: añadir las agregaciones a `catalog/jobs.py`; mezclaría responsabilidades de presentación con la cola.

### 3. Actualización automática por meta refresh

La plantilla incluye `<meta http-equiv="refresh" content="{{ refresh_seconds }}">`, con el intervalo tomado de configuración.

- **Por qué**: cumple el refresco sin JavaScript ni endpoints adicionales y funciona en cualquier navegador.
- **Alternativa descartada**: polling con `fetch` a una ruta JSON; añade estado en cliente y no es necesario para una página pequeña. La ruta `/health` sí devuelve JSON para el healthcheck.

### 4. Salud del worker desde el fichero de heartbeat

`worker_health()` comprueba la fecha de modificación de `settings.worker_heartbeat_file`; si no existe, usa el `heartbeat_at` más reciente de los trabajos `running`. Se considera `degraded` cuando supera `MEDIATECA_DASHBOARD_WORKER_STALE_SECONDS` (120 s por defecto) o cuando no hay ninguna referencia.

- **Por qué**: el worker ya toca el fichero en cada ciclo, incluso sin trabajos, y la base de datos cubre el caso de otro despliegue sin volumen compartido.
- **Alternativa descartada**: consultar solo `harvest_jobs`; un worker ocioso parecería caído.

### 5. Configuración por entorno

Se añaden a `Settings`: `dashboard_host` (`127.0.0.1`), `dashboard_port` (`8080`), `dashboard_refresh_seconds` (`15`), `dashboard_recent_limit` (`20`) y `dashboard_worker_stale_seconds` (`120`). Docker Compose sobrescribe el host a `0.0.0.0`.

- **Por qué**: mantiene el patrón `MEDIATECA_*` existente y permite ajustar la vista sin tocar código.
- **Alternativa descartada**: argumentos de CLI únicamente; el servicio de Compose necesita configuración declarativa.

### 6. Errores de base de datos controlados

Las rutas capturan `SQLAlchemyError`, registran el error y renderizan `degraded.html` con un mensaje genérico. `/health` responde siempre `200` mientras la aplicación viva, con un campo `db` que indica `ok` o `error`.

- **Por qué**: evita que Docker reinicie en bucle el dashboard cuando PostgreSQL falla y no filtra detalles internos.
- **Alternativa descartada**: devolver `503` en `/health` si la base de datos falla; convertiría una dependencia degradada en un reinicio continuo.

### 7. Despliegue como servicio adicional

Se añade al `docker-compose.yml` un servicio `dashboard` con la misma imagen `mediateca-enrich:local`, comando `python -m mediateca dashboard`, puerto `${MEDIATECA_DASHBOARD_PORT:-8080}:8080`, dependencia de `db` y healthcheck con `curl -fsS http://localhost:8080/health`.

- **Por qué**: reutiliza la imagen y el patrón de healthcheck ya usados por `worker`.
- **Alternativa descartada**: publicar la vista desde el portal; acoplaría este repositorio a otro despliegue.

## Risks / Trade-offs

- [Vista sin autenticación] → Se documenta como herramienta de operación para redes de confianza y se limita el bind local por defecto; en Compose se publica solo el puerto necesario.
- [Meta refresh recarga toda la página] → Aceptable para una página pequeña; no se pierde estado porque no hay formularios.
- [Consultas repetidas cada pocos segundos] → Los índices existentes en `harvest_jobs(status, job_type)` y `ediciones(detail_fetched_at)` mantienen las consultas baratas.
- [Heartbeat no compartido entre contenedores] → Se usa el `heartbeat_at` de la base de datos como respaldo.
- [Dependencias nuevas] → `fastapi`, `uvicorn` y `jinja2` se añaden al proyecto y a la imagen; son ligeras y no requieren servicios adicionales.

## Migration Plan

1. Añadir las dependencias y el módulo `dashboard`.
2. Configurar las variables `MEDIATECA_DASHBOARD_*` en `.env.example`.
3. Añadir el servicio `dashboard` a `docker-compose.yml` y los atajos al `Makefile`.
4. Ejecutar `docker compose up -d --build` y comprobar `http://localhost:8080`.
5. Rollback: detener y eliminar el servicio `dashboard`; no hay cambios de esquema ni de datos que revertir.
