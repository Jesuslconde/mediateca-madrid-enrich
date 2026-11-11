# Arquitectura de la ingesta

## Descubrimiento del catalogo

El descubrimiento enumera el catalogo de video del OPAC sin descargar las fichas de
detalle. Usa la consulta de truncamiento `*` con el filtro de formato `6`
(`Videos y DVD`) y `subcat=/`, de modo que incluye DVD, Blu-ray, 4K UHD y VHS.

La consulta se envia al formulario avanzado (`ACC=131`) con `xsqf01=*` y
`select03=6`. El OPAC devuelve los registros en orden `TITN` ascendente.

## Paginacion profunda

Cada pagina de resultados enlaza la siguiente mediante `ACC=161&DOC=N`. El cliente
recorre esos enlaces hasta que no hay pagina siguiente o se alcanza el limite
solicitado. El parametro `N` es la posicion del primer registro de la pagina y se
usa como cursor de reanudacion.

## Parser de listados

`parse_search_results` recorre los `li.c-docs_unit` de cada pagina y extrae el MARC
oculto (`span.js-*`): `TITN`, `T245`, `T260`, `FEPU`, `LENG`, `T300a`, `T655`,
`MATE` y, cuando existen, autores y notas. Con esos datos crea un `ParsedEdicion`
con metadatos basicos y el soporte detectado desde `T300a`.

## Checkpoint y reanudacion

El trabajo `discover` guarda en `harvest_jobs` el ultimo `DOC` y el ultimo `TITN`
procesados (`cursor_doc` y `cursor_titn`). Al reanudar se repite la busqueda `*` y
se salta al `DOC` guardado. El primer `TITN` leido se compara con el cursor para
detectar cambios del catalogo; si no coincide se registra una advertencia y se
continua desde el punto disponible.

## Sesion caducada

La sesion del OPAC caduca a los pocos minutos. Si ocurre durante la paginacion, el
cliente reabre sesion, repite la busqueda `*` y solicita la pagina `ACC=161&DOC=N`
del punto actual. No se reintenta la URL antigua, porque depende del contexto de
busqueda de la sesion anterior.

## Stubs, altas y bajas

Cada `TITN` descubierto se guarda como edicion stub (`is_stub=true`) con
`discovery_seen_at` y los metadatos basicos del listado. El upsert no sobrescribe
una edicion ya enriquecida: solo actualiza su fecha de ultima visualizacion.

En un descubrimiento completo, las ediciones con `discovery_seen_at` anterior al
inicio del trabajo que no han vuelto a aparecer se marcan con `missing_at`; nunca
se eliminan automaticamente. Las ediciones nuevas quedan pendientes de
enriquecimiento.

## Enriquecimiento por lotes

El enriquecimiento selecciona hasta 5.000 ediciones con `detail_fetched_at` vacio,
ordenadas por `TITN`, descarga la ficha de cada una mediante `?TITN=...&FORM=1`,
la parsea y actualiza la edicion y sus ejemplares. El lote termina cuando no quedan
`TITN` pendientes o se alcanza el limite.

A 1 peticion por segundo, un lote de 5.000 fichas tarda aproximadamente 1,4 horas;
la primera pasada completa de 67.215 fichas requiere unas 14 ejecuciones nocturnas.
El tamano del lote y el retardo son configurables desde `mediateca enrich`.

## Campos de enriquecimiento TMDB

La edicion conserva `pais` con el codigo del MARC del OPAC y añade
`paises_origen` con la lista de codigos ISO 3166-1 alfa-2 obtenida de TMDB,
`tmdb_id` y `tmdb_enriched_at`. La migracion `scripts/migrate_tmdb.sql` crea las
columnas de forma idempotente, indexa `tmdb_enriched_at` y actualiza
`schema_meta.schema_version` a `2`.

## Consulta a TMDB

Cuando existe un token efectivo (guardado en `app_config` o en
`MEDIATECA_TMDB_API_TOKEN`), el enriquecimiento consulta `/3/search/movie` con el
titulo y el ano de la edicion y, si hay una coincidencia fiable, `/3/movie/{id}`
para leer `production_countries` con respaldo de `origin_country`. El token puede
ser una API Key v3, enviada como `api_key`, o un Read Access Token v4, enviado
como `Authorization: Bearer`; el formato se detecta por la forma del token.

El emparejamiento normaliza titulos y exige un ano dentro de +-1 y una similitud
de al menos 0,90, o coincidencia exacta si la edicion no tiene ano. Los paises se
normalizan a codigos ISO 3166-1 alfa-2 en mayusculas y se deduplican. El cliente
aplica el retardo configurado, respeta `Retry-After` y reintenta errores
temporales con backoff. El token nunca se registra en logs.

## Cursor, reintentos y errores

El trabajo `enrich` guarda el ultimo `TITN` procesado en `cursor_titn` y actualiza
las estadisticas tras cada ficha. Si el worker se reinicia, el siguiente trabajo
continua desde el siguiente `TITN` pendiente y no repite las fichas ya marcadas con
`detail_fetched_at`.

Cada ficha se reintenta hasta el maximo configurado en el cliente del OPAC. Un fallo
persistente se registra en las estadisticas del trabajo y del `harvest_run`, se
excluye del lote activo y no bloquea al resto. La actualizacion es idempotente por
`TITN`; los ejemplares se sincronizan por `external_key` sin duplicarse.

## Sin snapshots

El enriquecimiento solo persiste datos normalizados en PostgreSQL. No escribe HTML
crudo ni crea archivos en `MEDIATECA_RAW_DIR`. La tabla `snapshots`, el modelo
`Snapshot`, la relacion `Edicion.snapshots` y `save_snapshot` se han retirado;
`scripts/migrate_ingesta.sql` elimina la tabla de forma idempotente.

## Indexacion incremental

Cada lote de descubrimiento o enriquecimiento indexa solo los `TITN` procesados
mediante `index_titns`, sin reconstruir el indice completo. Los `TITN` se consultan
y envian a Meilisearch en lotes de 200; los documentos no mencionados permanecen
intactos.

Cada documento incluye `detail_complete` e `is_stub`. Una edicion descubierta pero
sin `detail_fetched_at` se indexa como stub con `detail_complete=false`; al
enriquecerse se actualiza con `detail_complete=true` y los nuevos campos. Ambos
campos son filtrables. La API publica del portal aplica siempre
`detail_complete = true`, de modo que la web solo muestra fichas enriquecidas.

`paises_origen` se incluye en cada documento como lista (vacia si no hay TMDB),
es filtrable y se devuelve como faceta. Los TITN procesados por un lote se
indexan de forma incremental; tras un cambio de esquema o al anadir el campo a un
indice existente se ejecuta `mediateca index --reset` para reconstruirlo.

Si un lote falla antes de terminar, el worker indexa igualmente los `TITN` que ya
habia procesado. Ademas, el scheduler encola una reindexacion de reconciliacion
cada `index_interval_hours` (168 por defecto) para reparar cualquier divergencia
entre PostgreSQL y Meilisearch.

Si Meilisearch falla al terminar un lote, los `TITN` pendientes se guardan en
`harvest_jobs.stats.pending_index_titns`. El reintento del trabajo los indexa antes
de continuar con el siguiente lote. La reindexacion completa con
`index_editions(reset=True)` queda reservada al comando manual
`mediateca index --reset`, para cambios de esquema o reparaciones.

## Resolucion de captchas con FlareSolverr

La resolucion de captchas es opcional y esta desactivada por defecto. El cliente
del OPAC usa `httpx` como transporte normal y solo invoca a FlareSolverr cuando
detecta la pagina de reCAPTCHA y existe una URL efectiva configurada. La URL se
resuelve al crear cada cliente del OPAC y puede venir de la tabla `app_config`
(configuracion del dashboard) o de `MEDIATECA_FLARESOLVERR_URL`.

La configuracion persistida se guarda en `app_config`:

- `key`: nombre del ajuste, por ejemplo `flaresolverr_url`.
- `value`: valor en texto.
- `updated_at`: fecha de la ultima actualizacion.

`MEDIATECA_FLARESOLVERR_MAX_TIMEOUT_MS` controla el campo `maxTimeout` de la API de
FlareSolverr, en milisegundos. Por defecto es `60000`.

El cliente usa la API v1 de FlareSolverr mediante `POST {url}/v1` con
`cmd=request.get` o `cmd=request.post`. Para POST envia el formulario en `postData`
codificado como `application/x-www-form-urlencoded`; para GET incorpora los
parametros a la URL. Una respuesta valida tiene `status=ok` y
`solution.response`; de ella se usan el estado HTTP, la URL final, el HTML, las
cookies y el `userAgent`. Se asume una version de FlareSolverr con esta API v1.

FlareSolverr se invoca solo cuando la pagina del OPAC contiene el reCAPTCHA. Si no
hay URL, el servicio no responde o la respuesta sigue siendo un captcha, el
recolector registra el fallo y el trabajo se reprograma con el backoff existente,
sin reintentar la resolucion dentro de la misma peticion.

## Programacion de la ingesta

El servicio `scheduler` solo escribe en `harvest_jobs`; no descarga fichas ni
toca Meilisearch. Cada `MEDIATECA_SCHEDULER_POLL_SECONDS` lee la configuracion de
`app_config` y comprueba si toca encolar:

- `discover` incremental cada `discover_interval_hours` (12 por defecto);
- `discover` completo cada `full_sweep_interval_hours` (168 por defecto, `0` lo
  desactiva);
- `enrich` de los stubs nuevos si no hay un descubrimiento activo y quedan
  pendientes desde el ultimo descubrimiento completado.

El descubrimiento incremental reutiliza el `cursor_doc` y `cursor_titn` del ultimo
descubrimiento completado. El barrido completo semanal corrige posibles cambios
de orden del catalogo. Los jobs guardan `stats.mode` (`full` o `incremental`) y
`stats.reason`.

Si el OPAC devuelve un captcha que no se resuelve, el worker no consume el intento:
reencola el trabajo y pausa la ingesta `captcha_pause_minutes` minutos (30 por
defecto, configurable desde el dashboard).

Cuando un descubrimiento termina con nuevos registros, el worker encola
automaticamente un `enrich` con `stats.since = started_at` del descubrimiento.
`select_pending_titns` filtra por `discovery_seen_at >= since`, de modo que el
enriquecimiento programado procesa solo los stubs nuevos. El boton manual del
dashboard encola un enriquecimiento de todos los pendientes.

El dashboard permite encolar `discover`, `enrich` e `index` bajo demanda y editar
la programacion. Las acciones de escritura se protegen con
`MEDIATECA_DASHBOARD_ADMIN_TOKEN`: el operador introduce el token una vez y se
guarda en una cookie `HttpOnly` con `SameSite=Strict`.

## Dashboard de administracion

El dashboard sirve tres paginas con un menu lateral comun: Inicio (`/`), Tareas
(`/tareas`) y Configuracion (`/configuracion`). Inicio muestra la salud del
worker, el resumen de trabajos por estado y tipo, la cobertura y las metricas.
Tareas muestra la tabla de trabajos recientes y las acciones de descubrimiento,
enriquecimiento e indexacion. Configuracion agrupa la programacion, la URL de
FlareSolverr y el token de TMDB.

Inicio y Tareas incluyen `meta http-equiv="refresh"`; Configuracion no lo incluye
para no perder los formularios. Las rutas POST conservan su URL y redirigen a la
pagina de origen con `message` o `error`; el campo `next` se valida contra `/`,
`/tareas` y `/configuracion`. El estado de administracion y el login/logout viven
en el menu lateral.

## Observabilidad de la ingesta

El dashboard sirve tambien la API de observabilidad, siempre de solo lectura:

- `GET /api/ingest/status`: trabajos recientes, cobertura, metricas y salud del worker.
- `GET /api/ingest/coverage`: cobertura, metricas y salud del worker.

La cobertura incluye ediciones descubiertas, enriquecidas, pendientes, fallidas y
desaparecidas, ademas del porcentaje de enriquecimiento. Las metricas agregan
fichas procesadas, errores, captchas detectados, captchas resueltos, captchas
fallidos, renovaciones de sesion y tiempo medio por ficha a partir de
`harvest_jobs.stats`. El estado del worker usa el fichero de
heartbeat y, como respaldo, el `heartbeat_at` de la base de datos; se marca
`degraded` tras 120 segundos sin senal.

La CLI ofrece el mismo resumen con `mediateca ingest-status`. Los jobs de ingesta
escriben logs JSON con `job_id`, `job_type`, `titn`, `doc`, `result`,
`duration_ms` y `error`; no se registran datos personales.

## Ejecucion

- `mediateca discover --max-pages N --limit M`: ejecuta el descubrimiento y crea
  stubs. Sin `--max-pages` ni `--limit` recorre el catalogo completo.
- `mediateca enrich --limit 5000`: ejecuta un lote de enriquecimiento. El limite
  por defecto es 5.000 fichas.
- `mediateca discover --index` y `mediateca enrich --index` indexan solo el lote
  procesado; el worker indexa automaticamente al terminar cada trabajo.
- `mediateca index --reset`: reconstruye el indice completo, solo para cambios de
  esquema o reparaciones.
- `mediateca ingest-status`: muestra trabajos, cobertura, metricas y salud del
  worker.
- El worker procesa los trabajos `discover` y `enrich` de `harvest_jobs` con el
  mismo checkpoint y reanudacion.
