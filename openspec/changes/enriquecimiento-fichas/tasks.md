# Tasks

## 1. Retirada de snapshots

- [ ] 1.1 Eliminar `save_snapshot`, la relación `Edicion.snapshots` y el modelo `Snapshot`, y verificar que `Base.metadata.tables` no contiene `snapshots`
- [ ] 1.2 Eliminar la escritura de HTML en `Harvester._save` y verificar que un enriquecimiento no crea archivos en `MEDIATECA_RAW_DIR`
- [ ] 1.3 Añadir una migración idempotente para eliminar la tabla `snapshots` y verificar que se ejecuta dos veces sin error

## 2. Enriquecimiento

- [ ] 2.1 Implementar la selección de hasta 5.000 stubs pendientes ordenados por `titn` y verificar que no repite los ya enriquecidos
- [ ] 2.2 Implementar `harvest_enrichment` con fetch por TITN, parseo, upsert y `detail_fetched_at`, y verificar con un lote de 10 TITN
- [ ] 2.3 Implementar cursor por TITN, reintentos y registro de errores, y verificar que un fallo no bloquea el resto del lote
- [ ] 2.4 Añadir `mediateca enrich --limit 5000` y el tipo de trabajo `enrich`, y verificar que el worker lo ejecuta

## 3. Pruebas y documentación

- [ ] 3.1 Añadir tests de enriquecimiento idempotente y ausencia de snapshots, y verificar con `pytest -q`
- [ ] 3.2 Documentar el lote de 5.000, la duración estimada y la ausencia de snapshots en `docs/ARCHITECTURE.md` y `README.md`
- [ ] 3.3 Ejecutar `ruff check src tests` y verificar que no hay fallos
