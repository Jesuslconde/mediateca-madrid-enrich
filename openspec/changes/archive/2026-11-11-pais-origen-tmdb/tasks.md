# Tasks

## 1. Modelo compartido y migración

- [x] 1.1 Añadir `paises_origen` (JSON, por defecto `[]`), `tmdb_id` y `tmdb_enriched_at` a `Edicion`, y `paises_origen` a `SearchHit` y `RecordDetail` en `mediateca-madrid-shared`; subir `SCHEMA_VERSION` a `2` y la versión del paquete a `0.2.0`, y verificar con los tests del repositorio compartido y la generación del wheel `mediateca_shared-0.2.0-py3-none-any.whl`
- [x] 1.2 Sustituir el wheel de `vendor/` en `mediateca-madrid-enrich`, actualizar la dependencia `mediateca-shared` de `pyproject.toml` a `0.2.0`, y verificar que `pip install -e .` y `pytest -q` siguen funcionando con la nueva versión
- [x] 1.3 Añadir `scripts/migrate_tmdb.sql` idempotente con las tres columnas y la actualización de `schema_meta.schema_version` a `2`, añadirlo a `make migrate` y verificar ejecutándolo dos veces sobre PostgreSQL y consultando `\d ediciones` y `schema_meta`
- [x] 1.4 Documentar en `README.md` y `docs/ARCHITECTURE.md` los nuevos campos de la edición y el cambio de versión de esquema, y verificar que los nombres coinciden con el modelo compartido

## 2. Cliente TMDB y configuración

- [x] 2.1 Añadir `tmdb_api_token`, `tmdb_language`, `tmdb_delay`, `tmdb_timeout` y `tmdb_max_retries` a `Settings`, `.env.example` y al servicio `worker` de `docker-compose.yml`, y verificar con tests de valores por defecto y de ausencia de token
- [x] 2.2 Implementar `src/mediateca/catalog/tmdb.py` con autenticación para API Key v3 y Read Access Token v4, búsqueda de películas y consulta de detalle, y verificar con tests contra un transporte HTTP simulado para respuestas correctas, errores temporales, timeout, límite de peticiones y detección del formato del token
- [x] 2.3 Implementar la normalización de títulos, el emparejamiento por año con tolerancia de un año, la similitud mínima y la selección del mejor candidato, y verificar con tests de puntuación final del OPAC, remakes, años distintos, ausencia de año y coincidencia exacta
- [x] 2.4 Implementar la extracción de `production_countries` con respaldo de `origin_country`, normalización a mayúsculas y deduplicación, y verificar con tests de varios países, lista vacía y códigos duplicados
- [x] 2.5 Documentar en `README.md` y `docs/ARCHITECTURE.md` el contrato de la API de TMDB, las variables de configuración, la atribución exigida y los límites de uso, y verificar que los nombres documentados coinciden con `Settings`
- [x] 2.6 Implementar en `core/config_store.py` la clave `tmdb_api_token`, la validación del token y la resolución del token efectivo (dashboard, entorno o ninguno), y verificar con tests de precedencia, token guardado inválido, campo vacío y ausencia de token
- [x] 2.7 Añadir en `dashboard/queries.py` el estado de la configuración de TMDB (origen, activo y máscara), en `dashboard/app.py` la ruta `POST /config/tmdb` protegida por administración y en `templates/dashboard.html` la sección de configuración, y verificar con tests de guardado, conservación con campo vacío, borrado explícito, validación y error de persistencia
- [x] 2.8 Añadir tests que verifiquen que el HTML del dashboard no contiene el token completo y que los logs y errores de guardado, validación y uso no incluyen su valor, y documentar en `README.md` la sección, la precedencia y el procedimiento de borrado

## 3. Persistencia e integración con el enriquecimiento

- [x] 3.1 Implementar en `repository.py` la actualización idempotente de `paises_origen`, `tmdb_id` y `tmdb_enriched_at`, conservando `pais`, y verificar con tests de reenriquecimiento y de fallo después de una sincronización previa
- [x] 3.2 Integrar el enriquecimiento TMDB best-effort en `Harvester._enrich_titn` después de guardar la ficha del OPAC, resolviendo el token efectivo al inicio del trabajo, y verificar con tests de coincidencia, no coincidencia, ausencia de token, error de TMDB y propagación intacta de `CaptchaRequired`
- [x] 3.3 Añadir los contadores `tmdb_matched`, `tmdb_unmatched`, `tmdb_errors` y `tmdb_skipped` a las estadísticas del lote de enriquecimiento, y verificar con tests que se agregan correctamente y que un error de TMDB no incrementa los errores del OPAC
- [x] 3.4 Verificar con tests que el token guardado en el dashboard tiene prioridad sobre el entorno, que el entorno se usa como respaldo y que un cambio guardado durante un trabajo se aplica al siguiente

## 4. Backfill manual

- [x] 4.1 Añadir el comando `mediateca tmdb-enrich --limit N --delay S` que selecciona ediciones enriquecidas sin `tmdb_enriched_at`, resuelve el token efectivo, procesa el lote, informa de procesadas, emparejadas, sin coincidencia y fallidas, e indexa los TITN procesados salvo con `--no-index`, y verificarlo con tests de selección, reanudación y estadísticas
- [x] 4.2 Verificar con un test que el backfill sin token efectivo (ni en el dashboard ni en el entorno) termina con un error legible y no modifica ninguna edición
- [x] 4.3 Documentar en `README.md` el comando de backfill, su reanudación, el coste esperado y la necesidad de reindexar, y verificar que el comando documentado funciona como se describe

## 5. Índice y faceta

- [x] 5.1 Incluir `paises_origen` en `build_document`, en `FILTERABLE_ATTRIBUTES`, en `FACET_FIELDS` y en `build_filters`/`search`, y verificar con tests de documento con y sin países, filtro por uno o varios países y distribución de la faceta
- [x] 5.2 Verificar con un test que un documento antiguo sin `paises_origen` no rompe la búsqueda y que la reindexación completa con `--reset` reconstruye el campo
- [x] 5.3 Documentar en `README.md` y `docs/ARCHITECTURE.md` la nueva faceta, el filtro y la necesidad de `mediateca index --reset` tras el cambio de esquema, y verificar que las instrucciones coinciden con los comandos reales

## 6. Integración y verificación

- [x] 6.1 Ejecutar `pytest -q` y corregir cualquier fallo
- [x] 6.2 Ejecutar `ruff check src tests` y corregir cualquier aviso
- [x] 6.3 Sobre una base de datos migrada, ejecutar el backfill con un lote pequeño, comprobar que `paises_origen` aparece en PostgreSQL y en Meilisearch, y verificar la faceta y el filtro con una consulta de prueba
- [x] 6.4 Verificar que el cambio frontal de `mediateca-madrid` depende del wheel `0.2.0` y del índice reindexado, y anotar la entrega en el cambio dependiente
- [x] 6.5 Con el dashboard levantado, guardar un token, comprobar que el siguiente trabajo o backfill lo usa, borrarlo y verificar que cae al entorno o se desactiva, sin que el token aparezca en la vista ni en los logs

## Workflow follow-up

- Coordinación con `reorganizar-dashboard-paginas`: la sección de TMDB se movió de `/` a `/configuracion`; los formularios y los tests usan esa página.
- Archivar el cambio cuando la revisión del proyecto esté satisfecha.
- Verificar el resultado archivado y las specs principales actualizadas.
- Aplicar el cambio `filtro-pais-origen` en `mediateca-madrid` después de desplegar este cambio.
