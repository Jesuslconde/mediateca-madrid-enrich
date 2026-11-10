# Mediateca Madrid - enrich

Proyecto de ingesta, descubrimiento, enriquecimiento, worker, scheduler e indexacion del catalogo de Mediateca Madrid. Escribe en PostgreSQL y Meilisearch; la API y el portal solo leen de esos almacenamientos.

## Arranque

```bash
cp .env.example .env 2>/dev/null || true
make up
make migrate
make init
```

El worker procesa `harvest_jobs`; el scheduler solo planifica. La API y el portal se despliegan desde `mediateca-madrid`.

## Comandos

```bash
make help
make harvest q=cine pages=2 limit=20
make index
make worker-logs
make dashboard
make dashboard-logs
make test
make lint
make psql
```

El enriquecimiento completo se ejecuta en lotes de 5.000 fichas:

```bash
docker compose run --rm worker mediateca enrich --limit 5000
```

A 1 peticion por segundo cada lote tarda aproximadamente 1,4 horas. El trabajo
guarda un cursor por `TITN`, reintenta las fichas fallidas y solo persiste datos
parseados: no crea snapshots HTML ni escribe en `MEDIATECA_RAW_DIR`.

## Dashboard de estado

La vista web muestra en modo de solo lectura los trabajos por estado y tipo, los
trabajos recientes, la cobertura del catalogo y la salud del worker. La unica
escritura permitida es la seccion "Configuracion de FlareSolverr", que guarda o
borra una unica fila de configuracion. No crea ni modifica trabajos, ediciones,
ejemplares ni entradas del indice.

```bash
make dashboard        # Levanta el servicio dashboard en segundo plano
make dashboard-logs   # Sigue los logs del servicio
```

Queda disponible en `http://localhost:8080`. En local tambien se puede arrancar
con el comando de la CLI:

```bash
mediateca dashboard --host 127.0.0.1 --port 8080
```

La misma aplicacion expone la API de observabilidad de solo lectura:

```bash
curl http://localhost:8080/api/ingest/status
curl http://localhost:8080/api/ingest/coverage
```

Tambien se puede consultar desde la CLI:

```bash
docker compose run --rm worker mediateca ingest-status
```

Variables de configuracion:

- `MEDIATECA_DASHBOARD_HOST` y `MEDIATECA_DASHBOARD_PORT`: host y puerto de escucha.
- `MEDIATECA_DASHBOARD_REFRESH_SECONDS`: intervalo de refresco automatico de la pagina.
- `MEDIATECA_DASHBOARD_RECENT_LIMIT`: numero de trabajos recientes mostrados.
- `MEDIATECA_DASHBOARD_WORKER_STALE_SECONDS`: antiguedad maxima del heartbeat antes
  de marcar el worker como `degraded`.

## FlareSolverr

La resolucion de captchas esta desactivada por defecto. Solo se usa cuando existe
una URL base de FlareSolverr, configurada con `MEDIATECA_FLARESOLVERR_URL` o desde
la seccion "Configuracion de FlareSolverr" del dashboard. La URL del dashboard se
guarda en la tabla `app_config` y prevalece sobre la variable de entorno.

- `MEDIATECA_FLARESOLVERR_URL`: URL base de la instancia de FlareSolverr, por
  ejemplo `http://flaresolverr:8191`.
- `MEDIATECA_FLARESOLVERR_MAX_TIMEOUT_MS`: tiempo maximo de resolucion en
  milisegundos. Por defecto, `60000`.

FlareSolverr se usa solo como fallback: la recoleccion normal sigue con `httpx` y
FlareSolverr se invoca unicamente cuando el OPAC devuelve un reCAPTCHA. Si no hay
URL configurada o la resolucion falla, el trabajo se detiene y se reprograma con
el backoff existente. No se incluye un servicio FlareSolverr en `docker-compose.yml`;
hay que apuntar la variable o la configuracion del dashboard a una instancia propia.

Eludir un captcha puede contravenir las condiciones de uso del OPAC: la funcion
esta desactivada por defecto y el operador asume la decision de activarla. No
expongas el dashboard publicamente sin autenticacion: la URL editable podria
apuntar a servicios internos (SSRF), aunque solo se aceptan URLs `http`/`https`
sin credenciales.

## Programacion y tareas bajo demanda

El stack incluye un servicio `scheduler` que no ejecuta el OPAC: solo encola
trabajos en `harvest_jobs`. Por defecto:

- busca novedades cada 12 horas mediante descubrimiento incremental;
- hace un barrido completo del catalogo cada 7 dias como red de seguridad;
- encola el enriquecimiento de los nuevos registros despues de cada
  descubrimiento;
- evita duplicados si ya hay un trabajo activo del mismo tipo.

Los intervalos, el tamano de lote, el barrido completo y la activacion se guardan
en `app_config` y se editan desde la seccion "Programacion" del dashboard.

El dashboard tambien permite lanzar bajo demanda:

- "Buscar novedades": descubrimiento incremental.
- "Descubrimiento completo": recorre todo el catalogo.
- "Enriquecer pendientes": enriquece stubs pendientes.
- "Reindexar": encola una indexacion.

Variables relacionadas:

- `MEDIATECA_SCHEDULER_ENABLED`: valor por defecto si no hay configuracion en el
  dashboard.
- `MEDIATECA_SCHEDULER_POLL_SECONDS`: frecuencia con la que el scheduler revisa
  si toca encolar.
- `MEDIATECA_DASHBOARD_ADMIN_TOKEN`: token necesario para las acciones de
  escritura del dashboard. Si queda vacio, las acciones estan abiertas.

## Migraciones

- `scripts/migrate_disponibilidad.sql`: retirada del estado de prestamo.
- `scripts/migrate_ingesta.sql`: `harvest_jobs`, marcas de progreso, `schema_meta`
  y retirada idempotente de la tabla `snapshots`.
- `scripts/migrate_flaresolverr.sql`: tabla `app_config` para la configuracion
  persistida de FlareSolverr.

Todas son idempotentes. `make migrate` requiere PostgreSQL levantado.

## OpenSpec

La planificacion de ingesta vive en este repositorio. Los cambios `estado-ingesta`, `cola-worker`, `descubrimiento-catalogo`, `enriquecimiento-fichas`, `indexacion-incremental` y `observabilidad-ingesta` se migraron desde `mediateca-madrid`.
