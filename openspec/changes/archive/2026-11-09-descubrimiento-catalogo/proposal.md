# Proposal

## Why

La recolección actual solo procesa 20 resultados por consulta (`max_pages=2`) y no garantiza que se descubra todo el catálogo. Se ha verificado que la consulta con truncamiento `*` y formato `Videos y DVD` devuelve 67.215 registros y que la paginación profunda funciona hasta el final. Falta una fase de descubrimiento completa, reanudable y barata que cree la lista de TITN a enriquecer.

## What Changes

- Añadir el descubrimiento completo con `xsqf01=*`, `select03=6` y todas las variantes de vídeo, incluido VHS.
- Recorrer la paginación `ACC=161&DOC=N` de 10 en 10 hasta agotar los resultados.
- Parsear el MARC oculto de cada resultado (`li.c-docs_unit`) para extraer TITN y metadatos básicos.
- Crear ediciones stub para los TITN descubiertos.
- Guardar un checkpoint (`cursor_doc`, `cursor_titn`) y reanudar sin reiniciar.
- Reabrir sesión y volver a ejecutar la búsqueda si caduca durante la paginación.
- Detectar altas y bajas comparando el conjunto de TITN de descubrimientos consecutivos.
- Programar un descubrimiento semanal.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `ingesta-catalogo`: se añade el descubrimiento completo por truncamiento, el parser de listados, el checkpoint y la detección de altas/bajas.

## Impact

- `backend/src/mediateca/catalog/harvester.py`: búsqueda con truncamiento, paginación, checkpoints y recuperación de sesión.
- `backend/src/mediateca/catalog/parser.py`: nuevo parser de resultados de listado.
- `backend/src/mediateca/catalog/repository.py`: upsert de stubs y marcas de descubrimiento.
- `backend/src/mediateca/cli.py`: comando `discover`.
- `backend/src/mediateca/catalog/jobs.py`: tipo de trabajo `discover`.
- Tests con fixture de página de resultados.
