# Tasks

## 1. Indexador

- [ ] 1.1 Añadir `detail_complete` a `build_document` y verificar que una edición con `detail_fetched_at` vacío se marca como stub
- [ ] 1.2 Implementar `index_titns(titns)` con lotes de 200 y verificar que solo actualiza los TITN indicados
- [ ] 1.3 Añadir tests que comparen el número de documentos antes y después de indexar un lote

## 2. Integración con jobs

- [ ] 2.1 Llamar a `index_titns` al final de descubrimiento y enriquecimiento, y verificar que el lote queda indexado
- [ ] 2.2 Registrar los TITN pendientes de indexar si Meilisearch falla, y verificar que un reintento los procesa
- [ ] 2.3 Mantener `index_editions(reset=True)` solo para el comando manual `index --reset`

## 3. Pruebas y documentación

- [ ] 3.1 Ejecutar `pytest -q` y `ruff check src tests` y verificar que no hay fallos
- [ ] 3.2 Documentar la indexación incremental y el campo `detail_complete` en `docs/ARCHITECTURE.md`
