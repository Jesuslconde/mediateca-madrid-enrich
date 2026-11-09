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
enriquecerse se actualiza con `detail_complete=true` y los nuevos campos.

Si Meilisearch falla al terminar un lote, los `TITN` pendientes se guardan en
`harvest_jobs.stats.pending_index_titns`. El reintento del trabajo los indexa antes
de continuar con el siguiente lote. La reindexacion completa con
`index_editions(reset=True)` queda reservada al comando manual
`mediateca index --reset`, para cambios de esquema o reparaciones.

## Observabilidad de la ingesta

El dashboard sirve tambien la API de observabilidad, siempre de solo lectura:

- `GET /api/ingest/status`: trabajos recientes, cobertura, metricas y salud del worker.
- `GET /api/ingest/coverage`: cobertura, metricas y salud del worker.

La cobertura incluye ediciones descubiertas, enriquecidas, pendientes, fallidas y
desaparecidas, ademas del porcentaje de enriquecimiento. Las metricas agregan
fichas procesadas, errores, captchas, renovaciones de sesion y tiempo medio por
ficha a partir de `harvest_jobs.stats`. El estado del worker usa el fichero de
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
