# Design

## Context

Ver `proposal.md`. El índice actual se construye con `index_editions`, que recorre todas las ediciones y las envía en lotes de 200. Con 67k registros y lotes de ingesta de 5.000, reindexar todo es desproporcionado.

## Goals / Non-Goals

**Goals:**

- Indexar solo los TITN que cambian.
- Mostrar stubs en la búsqueda antes del enriquecimiento.
- Evitar reindexaciones completas accidentales.

**Non-Goals:**

- Cambiar el motor de búsqueda.
- Añadir nuevos campos facetables.
- Implementar búsqueda en vivo contra PostgreSQL.

## Decisions

### 1. `index_titns(titns)`

Se añade un método que consulta las ediciones por `TITN`, construye los documentos y los envía con `add_documents` en lotes de 200.

- **Por qué**: Meilisearch actualiza por clave primaria; no necesita reconstruir el índice.
- **Alternativa descartada**: reindexar todo tras cada lote; coste innecesario.

### 2. `detail_complete`

El documento incluye `detail_complete` y `is_stub`. Los stubs se indexan al descubrirse y se actualizan al enriquecerse.

- **Por qué**: el portal puede mostrar resultados desde el primer momento y el usuario sabe que la ficha está pendiente.
- **Alternativa descartada**: no indexar hasta el enriquecimiento; el portal estaría vacío durante días.

### 3. Indexación al final del lote

El worker llama a `index_titns` con los TITN procesados. Si la indexación falla, el trabajo queda en `failed` y se reintenta sin repetir el enriquecimiento.

- **Por qué**: desacopla el progreso de la actualización inmediata del índice.

### 4. Full reindex solo manual

`index_editions(reset=True)` queda para cambios de esquema o reparaciones. No se llama desde los jobs.

## Risks / Trade-offs

- [Documentos parciales] → `detail_complete=false` y actualización posterior.
- [Fallo de Meilisearch] → Reintento del trabajo de indexación; los datos en PostgreSQL son la fuente de verdad.
- [Índice desactualizado si se salta un lote] → El estado de ingesta registra los TITN pendientes de indexar.
- [Coste de consultar por TITN] → Índice por `titn` y lotes de 200.

## Migration Plan

1. Añadir `index_titns` y `detail_complete`.
2. Reindexar una vez con `mediateca index --reset` para introducir el campo.
3. Integrar la indexación en los jobs de descubrimiento y enriquecimiento.
4. Rollback: volver a `index_editions`; el campo adicional es inocuo.
