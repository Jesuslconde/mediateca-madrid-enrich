# busqueda-facetas Specification

## ADDED Requirements

### Requirement: Indexación incremental por TITN

El indexador MUST permitir indexar solo las ediciones indicadas por su `TITN`, sin reconstruir el índice completo.

#### Scenario: Indexar un lote

- **WHEN** termina un lote de enriquecimiento de 5.000 fichas
- **THEN** se envían a Meilisearch solo esos 5.000 documentos
- **AND** el resto del índice permanece intacto

### Requirement: Documentos stub

Una edición descubierta pero no enriquecida MUST indexarse como stub con los metadatos básicos y `detail_complete=false`.

#### Scenario: Stub visible

- **WHEN** el descubrimiento crea un stub
- **THEN** el documento aparece en la búsqueda con título, año, soportes y bibliotecas si se conocen
- **AND** el documento indica que la ficha está pendiente de enriquecer

### Requirement: Consistencia tras enriquecimiento

Al enriquecer una edición, el documento MUST actualizarse con los créditos, sinopsis, materias, ejemplares y `detail_complete=true`.

#### Scenario: Stub enriquecido

- **WHEN** termina el enriquecimiento de un TITN
- **THEN** el documento pierde la marca de stub
- **AND** la búsqueda muestra los nuevos campos

### Requirement: Reindexación completa controlada

La reindexación completa MUST ejecutarse solo con `--reset` explícito o tras un cambio de esquema, nunca automáticamente en cada lote.

#### Scenario: Cambio de esquema

- **WHEN** se añade un campo filtrable nuevo
- **THEN** el operador ejecuta `mediateca index --reset`
- **AND** se reconstruyen todos los documentos
