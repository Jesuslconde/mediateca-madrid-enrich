# Tasks

## 1. Parser y cliente

- [ ] 1.1 Implementar `parse_search_results` para extraer TITN y metadatos de `li.c-docs_unit`, y verificar con un fixture que obtiene TITN, título, año, idioma y `T300a`
- [ ] 1.2 Añadir `OpacClient.search_all()` con la consulta `*`, formato 6 y paginación profunda, y verificar que recorre varias páginas
- [ ] 1.3 Implementar la recuperación de sesión con re-búsqueda y salto al `DOC`, y verificar con una sesión invalidada simulada

## 2. Descubrimiento y stubs

- [ ] 2.1 Implementar `harvest_discovery` con checkpoint `cursor_doc`/`cursor_titn` y verificar que se reanuda sin duplicar TITN
- [ ] 2.2 Implementar el upsert de stubs con `is_stub`, `discovery_seen_at` y metadatos básicos, y verificar que no sobrescribe una edición ya enriquecida
- [ ] 2.3 Implementar la detección de altas y bajas y verificar que un TITN ausente se marca sin borrarse

## 3. CLI, pruebas y documentación

- [ ] 3.1 Añadir `mediateca discover --max-pages/--limit`, y verificar que crea stubs en una base de prueba
- [ ] 3.2 Añadir el tipo de trabajo `discover` a la cola y verificar que el worker lo ejecuta
- [ ] 3.3 Documentar la consulta `*`, el orden TITN y el checkpoint en `docs/ARCHITECTURE.md`
- [ ] 3.4 Ejecutar `pytest -q` y `ruff check src tests` y verificar que no hay fallos
