# Design

## Context

Ver `proposal.md`. La consulta `xsqf01=*` con `select03=6` devuelve 67.215 registros. La paginación `ACC=161&DOC=N` funciona hasta `DOC=67.101` y el orden es `TITN` ascendente. Cada página de resultados trae 10 registros (~120 KB) y MARC oculto con `TITN`, `T245`, `T260`, `FEPU`, `LENG`, `T300a`, `T655`, `MATE` y, en algunos casos, `T700`, `T511`, `T520`, `T521`, `T546` y `T024a`.

## Goals / Non-Goals

**Goals:**

- Descubrir todos los TITN de formato 6, incluido VHS.
- Crear stubs con metadatos básicos.
- Reanudar sin reiniciar y detectar altas/bajas.

**Non-Goals:**

- Descargar fichas de detalle en esta fase.
- Guardar HTML crudo de los listados.
- Enriquecer créditos, sinopsis o ejemplares.

## Decisions

### 1. Consulta `*` con formato 6

Se usa `xsqf01=*`, `select03=6`, `subcat=/`. No se filtra por DVD/Blu-ray para no perder VHS ni otros soportes; el filtro se aplica en la capa de búsqueda.

- **Por qué**: cobertura completa y una única enumeración.
- **Alternativa descartada**: particionar por años o letras; añade complejidad y huecos por acentos.

### 2. Descubrimiento barato por listado

Se parsea `li.c-docs_unit` y se guardan stubs. No se descarga la ficha de detalle en esta fase.

- **Por qué**: ~0,8 GB y ~1,9 h para 67k registros a 1 req/s, frente a ~28 GB y ~19 h del enriquecimiento.
- **Alternativa descartada**: descubrir y enriquecer en la misma pasada; impide reanudar y encarece el reintento.

### 3. Checkpoint por DOC y TITN

Cada lote guarda el último `DOC` y el último `TITN`. Al reanudar, se repite la búsqueda y se salta al `DOC`; se verifica el primer `TITN`.

- **Por qué**: el orden es estable por TITN ascendente y la verificación detecta cambios del catálogo.
- **Alternativa descartada**: guardar solo el TITN; no hay una consulta directa por rango de TITN.

### 4. Recuperación de sesión con re-búsqueda

La sesión caduca a los ~5 minutos. Si ocurre durante la paginación, se reabre, se repite `search("*")` y se salta al `DOC` actual.

- **Por qué**: la URL `ACC=161&DOC=N` depende del contexto de búsqueda de la sesión.
- **Alternativa descartada**: reintentar la misma URL tras renovar; devuelve una página sin contexto.

### 5. Stubs y marcas de descubrimiento

Se crea/actualiza una edición con `is_stub=true`, `discovery_seen_at` y metadatos básicos. El enriquecimiento la completa.

- **Por qué**: el portal puede mostrar resultados antes del enriquecimiento y la cola de trabajo es explícita.

## Risks / Trade-offs

- [Cambios del catálogo durante el descubrimiento] → Verificar el primer TITN y repetir el tramo si no coincide.
- [Sesión caducada] → Re-búsqueda y salto al DOC.
- [ReCAPTCHA por exceso de peticiones] → 1 req/s, parada y backoff; no eludir.
- [Resultados con MARC incompleto] → El stub guarda lo disponible; el enriquecimiento completa.
- [Pérdida de títulos con `*`] → Validar el total contra el contador de la página y revisar muestras.

## Migration Plan

1. Implementar el parser de listado y el cliente de descubrimiento.
2. Ejecutar un descubrimiento limitado (`--max-pages 2`) y verificar stubs.
3. Ejecutar el descubrimiento completo en un trabajo `discover`.
4. Programar un descubrimiento semanal.
5. Rollback: los stubs son idempotentes y pueden borrarse si no se han enriquecido.
