# cola-trabajos Specification

## Purpose

Ejecutar trabajos de ingesta largos y reanudables fuera del scheduler, con una cola persistente en PostgreSQL y un worker que procesa un trabajo cada vez.

## ADDED Requirements

### Requirement: Encolado de trabajos

El sistema MUST permitir encolar trabajos de tipo `discover`, `enrich` e `index` con un lote y un cursor inicial.

#### Scenario: Encolar enriquecimiento

- **WHEN** el scheduler encola un trabajo de enriquecimiento de 5.000 fichas
- **THEN** el trabajo queda en estado `pending`
- **AND** el worker puede reclamarlo

### Requirement: Reclamo atómico

El worker MUST reclamar un trabajo con una operación atómica que impida que dos workers ejecuten el mismo trabajo.

#### Scenario: Dos workers a la vez

- **WHEN** dos workers intentan reclamar el mismo trabajo
- **THEN** solo uno lo obtiene
- **AND** el otro recibe `NULL` o el siguiente trabajo disponible

### Requirement: Ejecución y heartbeat

El worker MUST actualizar un heartbeat mientras ejecuta un trabajo y SHALL marcar como fallido un trabajo cuyo heartbeat haya caducado.

#### Scenario: Worker caído

- **WHEN** un worker deja de actualizar el heartbeat
- **THEN** el trabajo puede ser reclamado de nuevo tras el timeout
- **AND** se registra el intento fallido

### Requirement: Reintentos y backoff

Los trabajos fallidos MUST reintentarse hasta `max_attempts` con backoff exponencial y SHALL terminar en `failed` cuando se agoten.

#### Scenario: Fallo temporal

- **WHEN** un trabajo falla por un error temporal
- **THEN** vuelve a `pending` con un intento más
- **AND** el siguiente intento espera un tiempo mayor

### Requirement: Concurrencia controlada

El sistema SHALL limitar la concurrencia a un trabajo de ingesta a la vez por defecto, configurable mediante variables de entorno.

#### Scenario: Un solo trabajo pesado

- **WHEN** hay un descubrimiento en ejecución
- **THEN** el worker no inicia otro descubrimiento o enriquecimiento
- **AND** los trabajos de indexación pueden esperar a que termine el lote
