# busqueda-facetas Specification

## Purpose
Ofrecer una búsqueda rápida y tolerante a errores sobre el catálogo de vídeos, con facetas que permitan acotar por soporte, género, año, idioma, biblioteca y disponibilidad.

## Requirements

### Requirement: Documento de índice

El indexador MUST construir un documento por edición con título, título uniforme, sinopsis, personas y roles, géneros, materias, soportes, año, idioma, país, duración, edad recomendada, EAN, bibliotecas tenedoras y número de ejemplares. El documento SHALL NOT incluir ningún campo de disponibilidad de préstamo.

#### Scenario: Edición indexada

- **WHEN** se indexa una edición con ejemplares en DVD
- **THEN** el documento contiene `soportes: ["DVD"]`
- **AND** contiene las bibliotecas tenedoras y el número de ejemplares
- **AND** no contiene ningún campo de disponibilidad

### Requirement: Búsqueda textual

La búsqueda SHALL usar los campos textuales principales y MUST devolver resultados paginados con puntuación de relevancia.

#### Scenario: Búsqueda por título

- **WHEN** el usuario busca `abejas`
- **THEN** aparecen los registros cuyo título o sinopsis contiene el término
- **AND** los resultados indican el total y la página actual

### Requirement: Facetas

La búsqueda MUST devolver distribuciones de facetas para `soporte`, `genero`, `anio`, `idioma` y `biblioteca`. La faceta de disponibilidad SHALL NOT existir.

#### Scenario: Faceta de soporte

- **WHEN** el usuario busca `cine` sin filtros
- **THEN** la respuesta incluye el número de resultados para DVD y Blu-ray
- **AND** no incluye una faceta de disponibilidad

### Requirement: Filtros combinados

El sistema SHALL combinar filtros de soporte, género, rango de años, idioma y biblioteca con la consulta textual. El filtro de disponibilidad SHALL NOT aceptarse.

#### Scenario: DVD disponibles en una biblioteca

- **WHEN** el usuario filtra por `soporte=DVD` y `biblioteca=B.P.M. Cardenal Cisneros`
- **THEN** solo se devuelven ediciones con al menos un ejemplar DVD en esa biblioteca
- **AND** no se ofrece ningún filtro por disponibilidad

### Requirement: Ordenación

Los resultados SHALL poder ordenarse por relevancia, año de publicación, título o duración.

#### Scenario: Orden por año descendente

- **WHEN** el usuario selecciona ordenar por año descendente
- **THEN** los resultados se muestran del más reciente al más antiguo

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
