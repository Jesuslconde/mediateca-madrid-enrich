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

## Ejecucion

- `mediateca discover --max-pages N --limit M`: ejecuta el descubrimiento y crea
  stubs. Sin `--max-pages` ni `--limit` recorre el catalogo completo.
- El worker procesa los trabajos `discover` de `harvest_jobs` con el mismo
  checkpoint y reanudacion.
