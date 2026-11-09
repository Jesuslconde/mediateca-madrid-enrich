# ingesta-catalogo Specification

## ADDED Requirements

### Requirement: Descubrimiento completo por truncamiento

El recolector MUST usar la consulta de truncamiento `*` con el filtro de formato `Videos y DVD` y SHALL recorrer toda la paginación hasta agotar los resultados.

#### Scenario: Catálogo completo

- **WHEN** se ejecuta el descubrimiento completo
- **THEN** se recorren todas las páginas de resultados
- **AND** se obtiene el conjunto de `TITN` de vídeo, DVD, Blu-ray, 4K UHD y VHS

#### Scenario: Orden estable

- **WHEN** el OPAC devuelve los resultados de `*`
- **THEN** el orden es `TITN` ascendente
- **AND** la paginación por `DOC` permite reanudar sin pérdidas

### Requirement: Parser de listado de resultados

El recolector MUST extraer de cada resultado el `TITN`, título, publicación, año, idioma, descripción física, géneros, materias y, cuando existan, autores y notas del MARC oculto.

#### Scenario: Resultado con MARC oculto

- **WHEN** se parsea un `li.c-docs_unit`
- **THEN** se obtiene al menos `TITN`, título y descripción física
- **AND** se detecta el soporte desde `T300a`

### Requirement: Checkpoint de descubrimiento

El descubrimiento MUST guardar el último `DOC` y el último `TITN` procesados y SHALL reanudar desde ese punto tras una interrupción.

#### Scenario: Reanudar tras fallo

- **WHEN** el descubrimiento se interrumpe en el registro 20.000
- **THEN** el siguiente trabajo empieza en el `DOC` guardado
- **AND** verifica que el primer `TITN` coincide con el cursor

### Requirement: Sesión durante paginación

Si la sesión caduca durante el descubrimiento, el recolector MUST reabrir sesión, repetir la búsqueda `*` y saltar al `DOC` actual.

#### Scenario: Sesión caducada en página profunda

- **WHEN** el OPAC devuelve la página de sesión expirada en `DOC=40001`
- **THEN** el cliente reabre sesión
- **AND** repite la búsqueda y continúa en el mismo `DOC`

### Requirement: Detección de altas y bajas

El descubrimiento SHALL marcar la fecha de última visualización de cada edición y SHALL identificar los `TITN` que han dejado de aparecer.

#### Scenario: Título nuevo

- **WHEN** aparece un `TITN` que no existía
- **THEN** se crea una edición stub
- **AND** queda pendiente de enriquecimiento

#### Scenario: Título desaparecido

- **WHEN** un `TITN` no aparece en un descubrimiento completo
- **THEN** se marca como no visto
- **AND** no se elimina automáticamente sin revisión
