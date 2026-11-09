# Design

## Context

Ver `proposal.md` para la motivación. El proyecto ya usa PostgreSQL, Docker Compose y una imagen de backend compartida por API y scheduler. No hay Redis ni RabbitMQ. La tabla `harvest_jobs` se introduce en el cambio `estado-ingesta`.

## Goals / Non-Goals

**Goals:**

- Ejecutar trabajos largos fuera del scheduler y de la API.
- Reanudar trabajos y evitar ejecuciones duplicadas.
- Mantener un único despliegue Docker y un único repositorio.

**Non-Goals:**

- Añadir Redis, RabbitMQ o Celery.
- Crear un proyecto separado de ingesta.
- Ejecutar varios enriquecimientos pesados en paralelo.

## Decisions

### 1. Monorepo con servicio worker, no proyecto separado

Se añade un servicio `worker` al `docker-compose.yml` usando la imagen `mediateca-backend:local`. Comparte modelos, parser, configuración y migraciones.

- **Por qué**: evita duplicar código y versiones; el despliegue sigue siendo un `docker compose up`.
- **Alternativa descartada**: repositorio/proyecto separado. Solo tendría sentido con equipos o escalados independientes; aquí duplicaría el modelo y el parser.

### 2. Cola en PostgreSQL con `FOR UPDATE SKIP LOCKED`

El worker reclama el siguiente trabajo `pending` con una transacción breve:

```sql
SELECT id FROM harvest_jobs
WHERE status = 'pending'
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

- **Por qué**: PostgreSQL ya está en el stack y ofrece reclamo atómico sin infraestructura extra.
- **Alternativa descartada**: Redis/RabbitMQ. Añade servicios y operación sin necesidad para 67k registros.

### 3. Scheduler solo encola

APScheduler deja de ejecutar ingestas largas. Sus jobs insertan trabajos en `harvest_jobs` y terminan. El worker ejecuta.

- **Por qué**: evita bloqueos, solapamientos y pérdida de trabajos al reiniciar el scheduler.

### 4. Un trabajo pesado a la vez

`MEDIATECA_WORKER_CONCURRENCY=1` por defecto. La indexación puede ejecutarse al final del lote dentro del mismo trabajo.

- **Por qué**: el OPAC no debe recibir dos crawlers a la vez y el rate limit se mantiene global.

### 5. Heartbeat y recuperación

El worker actualiza `heartbeat_at` cada 30 segundos. Un trabajo con heartbeat caducado vuelve a `pending` con un intento más.

## Risks / Trade-offs

- [Trabajo zombi] → Heartbeat y timeout de reclamación.
- [Duplicación por reintento] → Idempotencia por `TITN` y cursores.
- [Crecimiento de la tabla] → Retención y archivado de trabajos completados.
- [Worker único] → Suficiente para el volumen; se puede aumentar la concurrencia más adelante con `MEDIATECA_WORKER_CONCURRENCY`.

## Migration Plan

1. Aplicar `estado-ingesta`.
2. Añadir el servicio `worker` al compose.
3. Arrancar `docker compose up -d worker`.
4. Verificar que reclama un trabajo de prueba y actualiza heartbeat.
5. Rollback: detener el worker y volver a ejecutar las tareas por CLI.
