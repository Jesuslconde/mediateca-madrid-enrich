# Design

## Context

Ver `proposal.md`. La cola `harvest_jobs`, el worker y el dashboard ya existían. Faltaba un productor de trabajos y la posibilidad de operar la ingesta desde el dashboard.

## Goals / Non-Goals

**Goals:**

- Encolar trabajos desde el dashboard y el scheduler sin ejecutar la ingesta en esos procesos.
- Descubrir novedades de forma incremental y enriquecer solo los registros nuevos.
- Permitir cambiar intervalos y activación desde el dashboard sin reiniciar.
- Evitar trabajos duplicados y proteger las escrituras del dashboard.

**Non-Goals:**

- Resolver el captcha del OPAC, que se trata en el cambio de FlareSolverr.
- Añadir autenticación de usuario completa con gestión de cuentas.
- Cambiar el modelo de datos del catálogo.

## Decisions

### 1. Encolado centralizado en `catalog/jobs.py`

`enqueue_job()` crea el trabajo y comprueba si ya existe otro `pending` o `running` del mismo tipo. `enqueue_discover_job()` decide entre incremental y completo usando el último descubrimiento completado. `enqueue_enrich_job()` guarda `since` y el motivo en `stats`.

### 2. Configuración en `app_config`

Los intervalos, el lote y la activación se guardan como claves de `app_config`. El scheduler lee esa configuración en cada comprobación, por lo que el dashboard puede cambiarla sin reiniciar el contenedor. No hace falta una migración nueva.

### 3. Scheduler como servicio separado

`catalog/scheduler.py` implementa un bucle que comprueba cada `MEDIATECA_SCHEDULER_POLL_SECONDS` si toca encolar. El servicio no descarga fichas ni toca Meilisearch. Esto mantiene el scheduler independiente del dashboard y del worker.

### 4. Descubrimiento incremental por cursor

El scheduler usa el `cursor_doc` y `cursor_titn` del último descubrimiento completado. Si no existe, ejecuta un descubrimiento completo. Cada `full_sweep_interval_hours` se fuerza un descubrimiento completo para corregir posibles reordenaciones del catálogo.

### 5. Enriquecimiento encadenado y por intervalo

Al terminar un descubrimiento con registros nuevos, el worker encola un `enrich` con `since` igual al `started_at` del descubrimiento. El scheduler mantiene además una comprobación periódica para pendientes nuevos como red de seguridad. La selección filtra por `discovery_seen_at >= since` y `detail_fetched_at IS NULL`.

### 6. Dashboard con escrituras protegidas

Las acciones de escritura se protegen con `MEDIATECA_DASHBOARD_ADMIN_TOKEN`. El login guarda una cookie `HttpOnly` y `SameSite=Strict`. Si el token no está configurado, las escrituras quedan abiertas para desarrollo local. La lectura sigue siendo pública.

## Risks / Trade-offs

- [Supuesto de orden del catálogo] Los nuevos registros deben aparecer al final del cursor. → Barrido completo semanal configurable.
- [Duplicados] Varias fuentes pueden intentar encolar a la vez. → Comprobación de trabajos activos y rechazo con error.
- [Captcha] Un fallo de captcha detiene el descubrimiento o enriquecimiento. → Se mantiene la política de reintentos y el aviso en el dashboard.
- [Dashboard expuesto] El token viaja por HTTP si no hay TLS. → Restringir la red o publicar el dashboard detrás de HTTPS.
- [Scheduler caído] No se encolan trabajos nuevos. → El estado del worker y los jobs recientes permiten detectarlo; el scheduler es un servicio separado con reinicio automático.

## Migration Plan

1. Desplegar la imagen con los nuevos módulos.
2. Añadir el servicio `scheduler` y el token al stack.
3. Configurar los intervalos desde el dashboard.
4. Verificar que se encola un descubrimiento, que el worker lo procesa y que el enriquecimiento se encadena.
5. Rollback: desactivar la programación desde el dashboard y detener el servicio `scheduler`; los trabajos ya encolados pueden procesarse o cancelarse.
