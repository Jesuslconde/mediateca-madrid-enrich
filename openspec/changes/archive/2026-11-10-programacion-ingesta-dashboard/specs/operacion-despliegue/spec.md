# Spec Delta

## ADDED Requirements

### Requirement: Servicio scheduler en Docker Compose

El despliegue MUST incluir un servicio `scheduler` con la misma imagen del worker que solo encole trabajos y SHALL depender de la base de datos y de la inicialización del esquema.

#### Scenario: Arranque del scheduler

- **WHEN** se ejecuta el despliegue
- **THEN** el servicio `scheduler` arranca con la misma imagen de ingesta
- **AND** escribe trabajos en `harvest_jobs` sin ejecutar el OPAC

#### Scenario: Configuración desde el dashboard

- **WHEN** el operador cambia los intervalos en el dashboard
- **THEN** el scheduler usa la nueva configuración en su siguiente comprobación
- **AND** no requiere reiniciar el contenedor

### Requirement: Token de administración del dashboard

El despliegue MUST permitir configurar `MEDIATECA_DASHBOARD_ADMIN_TOKEN` y SHALL usar ese valor para autorizar las escrituras del dashboard.

#### Scenario: Token configurado

- **WHEN** el operador define `MEDIATECA_DASHBOARD_ADMIN_TOKEN`
- **THEN** las acciones de escritura requieren ese token
- **AND** la lectura del dashboard sigue siendo pública

#### Scenario: Token vacío

- **WHEN** la variable está vacía
- **THEN** el dashboard permite escrituras sin token
- **AND** se documenta que solo es adecuado para desarrollo local
