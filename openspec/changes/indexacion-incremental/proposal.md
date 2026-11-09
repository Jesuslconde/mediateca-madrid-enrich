# Proposal

## Why

Hoy cada recolección reindexa todas las ediciones (`index_editions`). Con 67.215 registros, un lote de 5.000 obligaría a reconstruir el índice completo. El portal necesita ver los stubs descubiertos y actualizar solo los TITN enriquecidos o refrescados.

## What Changes

- Añadir `index_titns(titns)` para indexar únicamente las ediciones indicadas.
- Incluir un campo `detail_complete` en el documento para distinguir stubs de fichas enriquecidas.
- Indexar el lote al terminar descubrimiento o enriquecimiento.
- Mantener `index_editions(reset=True)` solo para reconstrucciones completas y cambios de esquema.
- Evitar reindexaciones completas automáticas en cada job.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `busqueda-facetas`: se añade indexación incremental por TITN, documentos stub y reindexación completa controlada.

## Impact

- `backend/src/mediateca/catalog/indexer.py`: `index_titns`, `detail_complete`, actualización de documentos.
- `backend/src/mediateca/cli.py` y `catalog/jobs.py`: indexación tras cada lote.
- `backend/src/mediateca/api/schemas.py` y frontend: indicador de ficha pendiente si se expone.
- Tests del indexador y de documentos stub.
