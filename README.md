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

El backfill de paises de origen de TMDB se ejecuta por lotes sobre las ediciones
ya enriquecidas que aun no tienen `tmdb_enriched_at`:

```bash
docker compose run --rm worker mediateca tmdb-enrich --limit 5000 --delay 0.25
```

El comando reanuda por `TITN` las pendientes, no repite las ya sincronizadas y al
terminar indexa los TITN procesados; usa `--no-index` para omitir la indexacion.
Las ediciones sin coincidencia quedan sin marca y se reintentan en ejecuciones
posteriores. Requiere un token guardado en el dashboard o
`MEDIATECA_TMDB_API_TOKEN`.

## Dashboard de estado

La vista web se divide en tres paginas con un menu lateral comun:

- `Inicio` (`/`): salud del worker, trabajos por estado y tipo, cobertura del
  catalogo y metricas de ingesta.
- `Tareas` (`/tareas`): tabla de trabajos recientes y acciones de descubrimiento,
  enriquecimiento e indexacion.
- `Configuracion` (`/configuracion`): programacion, URL de FlareSolverr y token
  de TMDB.

Inicio y Tareas se refrescan automaticamente; Configuracion no, para no perder
los formularios mientras se editan. Las unicas escrituras son las secciones de
configuracion y el encolado de trabajos; no crea ni modifica ediciones,
ejemplares ni entradas del indice. Los mensajes de exito y error vuelven a la
pagina donde se origino la accion.

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

## TMDB

La obtencion del pais de origen con TMDB es opcional y esta desactivada mientras
no exista un token valido. El token puede ser una API Key v3 o un Read Access
Token v4; el cliente detecta el formato y usa `api_key` o `Authorization: Bearer`
segun corresponda.

El token se puede guardar desde la seccion "Configuracion de TMDB" del dashboard.
El valor guardado prevalece sobre `MEDIATECA_TMDB_API_TOKEN`; si no hay valor
guardado se usa la variable de entorno y, si tampoco existe, el enriquecimiento
TMDB se omite. El dashboard solo muestra una version enmascarada, no registra el
token en logs y permite borrarlo con una casilla explicita; guardar el campo vacio
conserva el token actual.

Variables de configuracion:

- `MEDIATECA_TMDB_API_TOKEN`: API Key v3 o Read Access Token v4.
- `MEDIATECA_TMDB_LANGUAGE`: idioma de busqueda; por defecto `es-ES`.
- `MEDIATECA_TMDB_DELAY`: segundos de espera entre peticiones; por defecto `0.25`.
- `MEDIATECA_TMDB_TIMEOUT`: timeout de cada peticion en segundos; por defecto `10`.
- `MEDIATECA_TMDB_MAX_RETRIES`: reintentos ante errores temporales; por defecto `3`.

El cliente consulta `/3/search/movie` para localizar la pelicula por titulo y ano
y `/3/movie/{id}` para obtener los paises de produccion. Si `production_countries`
esta vacio se usa `origin_country`. Los paises se guardan como codigos ISO 3166-1
alfa-2 en mayusculas y sin duplicados. El emparejamiento exige un ano dentro de
+-1 y una similitud de titulo de al menos 0,90, o coincidencia exacta si la ficha
no tiene ano.

TMDB limita el numero de peticiones. El cliente respeta `Retry-After`, aplica
backoff y usa el retardo configurado. El portal que muestre estos datos debe
incluir la atribucion exigida por TMDB ("This product uses the TMDB API but is
not endorsed or certified by TMDB."). No se cachean imagenes ni datos ajenos a
los campos normalizados del catalogo.

`paises_origen` se indexa como atributo filtrable y como faceta de Meilisearch.
Los lotes nuevos actualizan el indice de forma incremental; tras desplegar este
cambio o anadir el campo a un indice existente hay que reconstruirlo con
`mediateca index --reset`.

## Programacion y tareas bajo demanda

El stack incluye un servicio `scheduler` que no ejecuta el OPAC: solo encola
trabajos en `harvest_jobs`. Por defecto:

- busca novedades cada 12 horas mediante descubrimiento incremental;
- hace un barrido completo del catalogo cada 7 dias como red de seguridad;
- encola el enriquecimiento de los nuevos registros despues de cada
  descubrimiento;
- reconcilia el indice de Meilisearch una vez por semana;
- evita duplicados si ya hay un trabajo activo del mismo tipo.

Los intervalos, el tamano de lote, el barrido completo y la activacion se guardan
en `app_config` y se editan desde la seccion "Programacion" de la pagina
Configuracion del dashboard.

La pagina Tareas tambien permite lanzar bajo demanda:

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

La web publica consulta Meilisearch con el filtro `detail_complete=true`, por lo
que solo muestra fichas enriquecidas. Si el OPAC devuelve un captcha y no se
resuelve, el worker reencola el trabajo y pausa la ingesta durante los minutos
configurados en el dashboard.

## Modelo de datos y esquema

La edicion conserva `pais` con el codigo del MARC del OPAC y añade `paises_origen`
con la lista de codigos ISO 3166-1 alfa-2 obtenida de TMDB, `tmdb_id` y
`tmdb_enriched_at`. La version del esquema compartido se guarda en
`schema_meta.schema_version`; este cambio la sube a `2`.

## Migraciones

- `scripts/migrate_disponibilidad.sql`: retirada del estado de prestamo.
- `scripts/migrate_ingesta.sql`: `harvest_jobs`, marcas de progreso, `schema_meta`
  y retirada idempotente de la tabla `snapshots`.
- `scripts/migrate_flaresolverr.sql`: tabla `app_config` para la configuracion
  persistida de FlareSolverr.
- `scripts/migrate_tmdb.sql`: columnas `paises_origen`, `tmdb_id` y
  `tmdb_enriched_at`, indice de sincronizacion y `schema_version` 2.

Todas son idempotentes. `make migrate` requiere PostgreSQL levantado.

## OpenSpec

La planificacion de ingesta vive en este repositorio. Los cambios `estado-ingesta`, `cola-worker`, `descubrimiento-catalogo`, `enriquecimiento-fichas`, `indexacion-incremental` y `observabilidad-ingesta` se migraron desde `mediateca-madrid`.
