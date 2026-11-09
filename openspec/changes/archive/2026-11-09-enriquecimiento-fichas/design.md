# Design

## Context

Ver `proposal.md`. El descubrimiento crea stubs para 67.215 TITN. La ficha de detalle pesa ~419 KB y trae créditos, sinopsis, materias y ejemplares. La sesión caduca a los ~5 minutos, pero las URLs por `TITN` son estables y se pueden rebindear al renovar.

## Goals / Non-Goals

**Goals:**

- Enriquecer todos los TITN en lotes de 5.000.
- Reanudar por cursor y no duplicar datos.
- Guardar solo datos parseados.
- Mantener un ritmo de 1 req/s.

**Non-Goals:**

- Descubrir nuevos TITN; eso corresponde al cambio `descubrimiento-catalogo`.
- Refrescar disponibilidad: se elimina del producto en `simplificar-disponibilidad-bibliotecas`.
- Guardar snapshots HTML o permitir reproceso sin red.

## Decisions

### 1. Lote de 5.000 por trabajo

Se seleccionan hasta 5.000 ediciones con `detail_fetched_at IS NULL`, ordenadas por `titn`. Cada lote tarda ~1,4 h a 1 req/s y encaja en una ejecución nocturna.

- **Por qué**: equilibrio entre avance y duración; 14 noches para la primera pasada completa.
- **Alternativa descartada**: 20 h seguidas; más frágil y menos social con el OPAC.

### 2. Sin snapshots

Se elimina `save_snapshot`, la relación `Edicion.snapshots` y el modelo `Snapshot`. La migración elimina la tabla.

- **Por qué**: el usuario quiere solo datos parseados; se ahorran ~28 GB y la lógica de hashes.
- **Alternativa descartada**: guardar snapshots comprimidos. Se descarta por decisión explícita del usuario.

### 3. Ficha por TITN y rebind de sesión

Cada ficha se pide con `?TITN=...&FORM=1`. Si la sesión caduca, se reabre y se rebindea la URL; no hace falta conservar el contexto de búsqueda.

- **Por qué**: las URLs por TITN son independientes del conjunto de resultados.
- **Alternativa descartada**: reutilizar la URL de la lista con `DOC`; depende de la sesión y del orden.

### 4. Idempotencia por TITN y `external_key`

`upsert_edicion` actualiza la edición y sincroniza ejemplares por `external_key`. Repetir un lote no crea duplicados.

- **Por qué**: los reintentos y las reejecuciones son seguros.

### 5. Índice tras el lote

Al terminar un lote se indexan solo los TITN procesados (depende de `indexacion-incremental`). No se reindexa todo el catálogo.

## Risks / Trade-offs

- [Sesión caducada] → Rebind por TITN y reintento.
- [Ficha con muchos ejemplares] → El parser ya maneja 70+; se prueba con una ficha real.
- [Fallo a mitad de lote] → Commit por ficha y cursor por TITN.
- [Pérdida de capacidad de reproceso] → Se acepta a cambio de no almacenar HTML.
- [Duración de 14 noches] → Se puede aumentar el lote o la concurrencia si el OPAC lo tolera.

## Migration Plan

1. Aplicar `estado-ingesta`.
2. Implementar el enriquecimiento por lotes y eliminar snapshots.
3. Ejecutar un lote de prueba de 10 TITN y verificar datos y ausencia de archivos.
4. Encolar lotes de 5.000 hasta completar la cobertura.
5. Rollback: restaurar el código anterior y reactivar snapshots si se necesitan; los datos parseados permanecen.
