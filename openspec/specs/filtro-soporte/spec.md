# filtro-soporte Specification

## Purpose
Distinguir de forma fiable DVD, Blu-ray y otros soportes dentro de los registros de vídeo, para que el portal pueda ofrecer ese filtro aunque el OPAC los agrupe bajo una única etiqueta.

## Requirements

### Requirement: Detección desde la descripción física

El clasificador MUST inspeccionar el campo de descripción física (`MARC 300$a`) y detectar `DVD`, `Blu-ray`, `4K UHD` y `VHS`.

#### Scenario: Descripción de DVD

- **WHEN** la descripción física es `1 DVD-Video (ca. 129 min) : son., col. ; 12 cm`
- **THEN** el soporte detectado es `DVD`

#### Scenario: Descripción de Blu-ray

- **WHEN** la descripción física es `1 Blu-ray (ca. 129 min) : son., col.`
- **THEN** el soporte detectado es `Blu-ray`

### Requirement: Detección desde los ejemplares

El clasificador SHALL revisar el campo `Soporte` de cada ejemplar y SHALL añadir el soporte normalizado resultante.

#### Scenario: Soporte por ejemplar

- **WHEN** un ejemplar tiene `Soporte = Vídeo (Blu-Ray)`
- **THEN** el ejemplar se clasifica como `Blu-ray`
- **AND** la edición agrega `Blu-ray` a sus soportes

### Requirement: Normalización de variantes

Las variantes `Blu-ray`, `Blu-Ray`, `BluRay`, `BD` y `Blu ray` MUST normalizarse a un único valor `Blu-ray`; las variantes de DVD SHALL normalizarse a `DVD`.

#### Scenario: Variantes de escritura

- **WHEN** un registro contiene `Vídeo (Blu-Ray)` y otro `Blu-ray`
- **THEN** ambos se indexan con el mismo valor de faceta `Blu-ray`

### Requirement: Ediciones con varios soportes

Una edición que contenga ejemplares de varios soportes MUST conservar todos ellos; el sistema no SHALL forzar un único soporte si los datos no lo permiten.

#### Scenario: Pack DVD + Blu-ray

- **WHEN** una edición tiene ejemplares DVD y Blu-ray
- **THEN** `soportes` contiene ambos valores
- **AND** el filtro por cualquiera de los dos encuentra la edición

### Requirement: Filtro de soporte en la API

La API MUST aceptar uno o varios valores de soporte y SHALL aplicar la lógica `OR` entre ellos y `AND` con el resto de filtros.

#### Scenario: Filtro DVD o Blu-ray

- **WHEN** la petición incluye `soporte=DVD` y `soporte=Blu-ray`
- **THEN** se devuelven ediciones que tengan al menos uno de los dos soportes
