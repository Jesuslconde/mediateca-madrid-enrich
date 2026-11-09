# estado-ingesta Specification

## Purpose

Persistir el estado de los trabajos de ingesta masiva y el progreso por edición para que descubrimiento, enriquecimiento e indexación sean reanudables, idempotentes y observables.

## ADDED Requirements

### Requirement: Trabajos de ingesta persistentes

El sistema MUST almacenar cada trabajo de ingesta con un identificador, tipo, estado, cursor, contadores y fechas de inicio y fin.

#### Scenario: Trabajo en curso

- **WHEN** el worker empieza un trabajo de enriquecimiento
- **THEN** el trabajo queda en estado `running` con su cursor inicial
- **AND** al terminar queda en `completed` o `failed` con estadísticas

#### Scenario: Reanudación tras un fallo

- **WHEN** un trabajo queda interrumpido
- **THEN** el siguiente worker puede reanudarlo desde el último cursor persistido
- **AND** no vuelve a procesar los registros ya completados

### Requirement: Marcas de progreso por edición

Cada edición MUST registrar cuándo fue descubierta y cuándo se enriqueció su ficha.

#### Scenario: Edición recién descubierta

- **WHEN** el descubrimiento encuentra un `TITN` nuevo
- **THEN** crea una edición stub con `discovery_seen_at`
- **AND** deja `detail_fetched_at` vacío hasta el enriquecimiento

#### Scenario: Edición enriquecida

- **WHEN** se procesa la ficha completa de un `TITN`
- **THEN** se actualiza `detail_fetched_at`
- **AND** la edición deja de considerarse stub

### Requirement: Cursores de descubrimiento

El descubrimiento MUST guardar el último `DOC` y el último `TITN` procesados para poder continuar sin reiniciar la paginación.

#### Scenario: Continuar descubrimiento

- **WHEN** se reanuda un descubrimiento interrumpido
- **THEN** el cliente vuelve a ejecutar la búsqueda y salta al `DOC` guardado
- **AND** verifica que el primer `TITN` de la página coincide con el cursor

### Requirement: Idempotencia

Repetir un descubrimiento o un enriquecimiento MUST actualizar los registros existentes por `TITN` sin crear duplicados.

#### Scenario: Reprocesar una edición

- **WHEN** se vuelve a enriquecer un `TITN` ya existente
- **THEN** se actualizan sus datos y sus ejemplares
- **AND** no se crea una segunda edición con el mismo `TITN`

### Requirement: Consulta de estado

El sistema SHALL exponer el estado de los trabajos, los registros pendientes y la cobertura del catálogo desde CLI y API.

#### Scenario: Estado de la ingesta

- **WHEN** el operador consulta el estado
- **THEN** ve trabajos activos, completados y fallidos
- **AND** ve cuántas ediciones están descubiertas, enriquecidas y pendientes
