# Proposal

## Why

El catálogo solo conoce el país que aparece en el MARC del OPAC, a menudo ausente, abreviado o limitado a un único valor. Ese dato no permite ofrecer un filtro fiable por país de origen en el portal. TMDB aporta los países de producción normalizados de cada película y permite construir una faceta útil sin depender de la calidad del registro bibliográfico. Además, el operador debe poder configurar el token de TMDB desde el dashboard, sin editar variables de entorno ni reconstruir el despliegue.

## What Changes

- Añadir un cliente de TMDB que, a partir del título y el año de la edición, localice la película y obtenga sus países de producción.
- Persistir en cada edición una lista normalizada de países de origen (`paises_origen`) junto con el identificador de TMDB y la marca de sincronización, sin borrar el `pais` original del OPAC.
- Ejecutar el enriquecimiento TMDB de forma complementaria al enriquecimiento del OPAC: las fichas nuevas lo obtienen al enriquecerse y un comando manual permite rellenar las ediciones ya existentes.
- Tratar TMDB como una fuente opcional y tolerante a fallos: sin token configurado se omite; un fallo de TMDB no invalida el enriquecimiento del OPAC y queda pendiente para el backfill.
- Indexar `paises_origen` como atributo filtrable y como faceta de Meilisearch, de modo que la API pueda filtrar y el portal mostrar la distribución por país.
- Añadir configuración para el token de API, el idioma de consulta, el retardo entre peticiones y los reintentos.
- Añadir al dashboard una sección "Configuración de TMDB" para guardar, actualizar o borrar el token de API, persistido en `app_config` y con precedencia sobre `MEDIATECA_TMDB_API_TOKEN`. El token SHALL mostrarse enmascarado y nunca registrarse en logs.
- Aceptar tanto una API Key v3 como un Read Access Token v4 de TMDB, detectando el formato para usar `api_key` o `Authorization: Bearer`.
- **BREAKING**: el modelo compartido gana columnas nuevas y sube la versión de esquema; la API y el portal de `mediateca-madrid` deberán actualizar el wheel compartido antes de leer los nuevos campos.
- El filtro visible en la web frontal se planifica como un cambio separado en el repositorio `mediateca-madrid`; este cambio solo deja preparados el dato y la faceta en PostgreSQL y Meilisearch.

## Capabilities

### New Capabilities

- `enriquecimiento-tmdb`: consulta TMDB para obtener los países de producción de una edición, con emparejamiento por título y año, normalización, manejo de errores, backfill manual y configuración.

### Modified Capabilities

- `modelo-catalogo`: se añaden a la edición los campos `paises_origen`, `tmdb_id` y `tmdb_enriched_at`, y se define la conservación del `pais` del OPAC como dato independiente.
- `busqueda-facetas`: el documento de índice incluye `paises_origen` como atributo filtrable y la búsqueda devuelve su distribución como faceta.
- `dashboard-ingesta`: se permite configurar el token de TMDB desde el dashboard con precedencia sobre la variable de entorno, mostrando solo una versión enmascarada y sin registrar el valor en logs.

## Impact

- `mediateca-madrid-shared`: nuevas columnas en `mediateca_shared.models.Edicion`, `paises_origen` en `SearchHit` y `RecordDetail`, y subida de `SCHEMA_VERSION`; hay que reconstruir el wheel y actualizar los vendors de `mediateca-madrid-enrich` y `mediateca-madrid`.
- `src/mediateca/catalog/` (nuevo cliente TMDB): búsqueda de película, detalle de países, emparejamiento y normalización.
- `src/mediateca/catalog/harvester.py` y `repository.py`: integración tras el enriquecimiento del OPAC y actualización idempotente de la edición.
- `src/mediateca/catalog/indexer.py`: `paises_origen` en el documento y en `filterableAttributes`; `paises_origen` en `FACET_FIELDS` y en `build_filters`.
- `src/mediateca/core/config.py`, `.env.example` y `docker-compose.yml`: token de TMDB, idioma, retardo y reintentos.
- `src/mediateca/core/config_store.py`: normalización, lectura, escritura y resolución del token efectivo de TMDB.
- `src/mediateca/dashboard/app.py`, `queries.py` y `templates/dashboard.html`: sección "Configuración de TMDB", ruta de guardado/borrado, estado, origen y máscara del token.
- `src/mediateca/cli.py`: comando manual de backfill TMDB.
- `scripts/`: migración idempotente de columnas e índice; actualización de la versión de esquema.
- `tests/`: cliente TMDB simulado, emparejamiento, normalización, persistencia, reintentos, índice y backfill.
- `README.md` y `docs/ARCHITECTURE.md`: comportamiento, configuración, límites de uso y dependencia del cambio frontal.
- Dependencias externas: API de TMDB y un token válido; sin librerías Python nuevas.
- Cambio dependiente en `mediateca-madrid`: filtro por país en la API y en el portal, planificado aparte.
