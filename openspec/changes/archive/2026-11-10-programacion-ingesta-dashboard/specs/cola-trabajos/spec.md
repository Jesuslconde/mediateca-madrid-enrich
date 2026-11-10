# Spec Delta

## MODIFIED Requirements

### Requirement: Encolado de trabajos

El sistema MUST permitir encolar trabajos de tipo `discover`, `enrich` e `index` con un lote y un cursor inicial desde la CLI, el dashboard o el scheduler.

#### Scenario: Encolar enriquecimiento

- **WHEN** el scheduler encola un trabajo de enriquecimiento de 5.000 fichas
- **THEN** el trabajo queda en estado `pending`
- **AND** el worker puede reclamarlo

#### Scenario: Encolar desde el dashboard

- **WHEN** el operador solicita un trabajo bajo demanda
- **THEN** se crea un trabajo `pending` con el tipo y lote solicitados
- **AND** el dashboard no ejecuta la ingesta

## ADDED Requirements

### Requirement: Deduplicación de trabajos

El sistema MUST impedir que existan dos trabajos activos del mismo tipo y SHALL devolver un error comprensible cuando se intente encolar un duplicado.

#### Scenario: Duplicado activo

- **WHEN** ya hay un `discover`, `enrich` o `index` en estado `pending` o `running`
- **THEN** un nuevo encolado del mismo tipo se rechaza
- **AND** el trabajo existente no se modifica

### Requirement: Programación periódica

El scheduler MUST encolar los trabajos programados sin ejecutar el OPAC y SHALL leer la configuración desde `app_config` en cada comprobación.

#### Scenario: Descubrimiento programado

- **WHEN** se cumple el intervalo de descubrimiento
- **THEN** el scheduler encola un `discover` incremental
- **AND** no encola otro si ya hay uno activo

#### Scenario: Barrido completo programado

- **WHEN** se cumple el intervalo de barrido completo
- **THEN** el scheduler encola un `discover` completo
- **AND** el modo queda registrado en las estadísticas del trabajo

#### Scenario: Enriquecimiento programado

- **WHEN** hay stubs nuevos pendientes desde el último descubrimiento completado y se cumple el intervalo de enriquecimiento
- **THEN** el scheduler encola un `enrich` con el filtro temporal correspondiente
- **AND** no encola otro si ya hay un descubrimiento o enriquecimiento activo

### Requirement: Enriquecimiento encadenado

Al terminar un descubrimiento con nuevos registros, el worker MUST encolar un enriquecimiento para esos registros y SHALL evitar duplicados.

#### Scenario: Descubrimiento con novedades

- **WHEN** un `discover` termina habiendo procesado al menos un registro nuevo
- **THEN** se encola un `enrich` con `since` igual al inicio del descubrimiento
- **AND** el enriquecimiento procesa solo los stubs descubiertos desde ese instante

#### Scenario: Descubrimiento sin novedades

- **WHEN** un `discover` termina sin registros nuevos
- **THEN** no se encola ningún enriquecimiento automático
