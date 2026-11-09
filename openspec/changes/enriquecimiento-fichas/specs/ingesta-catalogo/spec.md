# ingesta-catalogo Specification

## ADDED Requirements

### Requirement: Enriquecimiento completo por lotes

El sistema MUST enriquecer todas las ediciones descubiertas en lotes de 5.000 por defecto, actualizando metadatos, créditos, materias y ejemplares.

#### Scenario: Lote de 5.000 fichas

- **WHEN** se ejecuta un trabajo de enriquecimiento
- **THEN** selecciona hasta 5.000 TITN pendientes
- **AND** al terminar el lote actualiza el cursor y las estadísticas

#### Scenario: Cobertura completa

- **WHEN** no quedan TITN con `detail_fetched_at` vacío
- **THEN** el trabajo termina y la cobertura de enriquecimiento es del 100%
- **AND** se registra en el estado de ingesta

### Requirement: Solo datos parseados

El enriquecimiento MUST persistir únicamente datos normalizados en PostgreSQL y MUST NOT guardar HTML crudo ni snapshots.

#### Scenario: Ficha procesada

- **WHEN** se enriquece un TITN
- **THEN** se guardan sus campos, personas, materias, enlaces y ejemplares
- **AND** no se crea ningún archivo de snapshot

### Requirement: Reanudación por TITN

El enriquecimiento MUST guardar el último `TITN` procesado y SHALL reanudar desde el siguiente pendiente tras un fallo.

#### Scenario: Reinicio del worker

- **WHEN** el worker se reinicia a mitad de un lote
- **THEN** el siguiente trabajo continúa desde el último `TITN` persistido
- **AND** no repite las fichas ya marcadas con `detail_fetched_at`

### Requirement: Errores y reintentos

Una ficha fallida MUST registrarse, reintentarse hasta el máximo configurado y SHALL excluirse del lote activo tras agotar los intentos.

#### Scenario: Ficha con error persistente

- **WHEN** una ficha falla tres veces
- **THEN** se marca con error y no bloquea el resto del lote
- **AND** queda visible para revisión manual

### Requirement: Actualización idempotente de ejemplares

Repetir el enriquecimiento de un TITN MUST actualizar sus ejemplares existentes por `external_key` sin duplicarlos.

#### Scenario: Reenriquecer una edición

- **WHEN** se procesa de nuevo un TITN ya enriquecido
- **THEN** se actualizan sus ejemplares y relaciones
- **AND** no se crean duplicados

## REMOVED Requirements

### Requirement: Persistencia de snapshots

**Reason**: El usuario ha decidido guardar solo datos parseados; el HTML crudo ocupa ~28 GB en una pasada completa y no se necesita para el portal.

**Migration**: Se deja de escribir HTML, se eliminan `save_snapshot`, la relación `Edicion.snapshots` y la tabla `snapshots`. Los snapshots existentes pueden borrarse con una migración idempotente.
