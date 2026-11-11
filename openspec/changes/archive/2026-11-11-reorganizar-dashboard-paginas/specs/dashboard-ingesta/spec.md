# Spec Delta

## ADDED Requirements

### Requirement: Menú lateral de navegación

El dashboard MUST mostrar un menú lateral persistente en las páginas de Inicio, Tareas y Configuración, con enlaces a `/`, `/tareas` y `/configuracion`, la sección activa resaltada y acceso al estado de administración, login y logout.

#### Scenario: Navegación entre páginas

- **WHEN** el operador pulsa una opción del menú lateral
- **THEN** se abre la página correspondiente sin recargar la aplicación completa
- **AND** el menú sigue visible en la nueva página

#### Scenario: Sección activa

- **WHEN** el operador está en una de las tres páginas
- **THEN** el menú resalta la opción de esa página
- **AND** las demás opciones siguen disponibles

#### Scenario: Administración desde el menú

- **WHEN** el operador necesita iniciar o cerrar sesión de administración
- **THEN** dispone de esas acciones en el menú lateral desde cualquier página
- **AND** el estado de la sesión se muestra en el menú

### Requirement: Página de Inicio centrada en estados

La página de Inicio MUST mostrar únicamente la salud del worker, el resumen de trabajos por estado y tipo, la cobertura del catálogo y las métricas de ingesta. SHALL NOT incluir la tabla de trabajos recientes, las acciones de encolado ni los formularios de configuración.

#### Scenario: Inicio sin administración

- **WHEN** el operador abre `/`
- **THEN** ve los estados, la cobertura y las métricas
- **AND** no ve la tabla de trabajos recientes, los botones de encolado ni los formularios de configuración

#### Scenario: Acceso a las demás páginas

- **WHEN** el operador necesita ver trabajos o cambiar configuración
- **THEN** el menú lateral le ofrece Tareas y Configuración
- **AND** Inicio no duplica esas secciones

### Requirement: Página de Tareas

La página de Tareas MUST mostrar los trabajos recientes y las acciones de descubrimiento, enriquecimiento e indexación. SHALL conservar las reglas de encolado, la desactivación de acciones con un trabajo activo y la protección de escritura.

#### Scenario: Visualización de trabajos

- **WHEN** el operador abre `/tareas`
- **THEN** ve la tabla de trabajos recientes con los mismos campos y orden que antes
- **AND** ve el estado activo de cada tipo de trabajo

#### Scenario: Acciones bajo demanda

- **WHEN** el operador pulsa una acción de descubrimiento, enriquecimiento o indexación
- **THEN** se encola el trabajo con las mismas reglas que en la vista anterior
- **AND** las acciones con un trabajo activo del mismo tipo siguen deshabilitadas

#### Scenario: Redirección con mensaje

- **WHEN** una acción de tareas termina con éxito o error
- **THEN** el operador vuelve a `/tareas`
- **AND** ve el mensaje correspondiente en esa página

#### Scenario: Escritura sin administración

- **WHEN** el operador no tiene sesión de administración y hay token configurado
- **THEN** las acciones de encolado aparecen deshabilitadas o se rechazan
- **AND** no se crea ningún trabajo

### Requirement: Página de Configuración

La página de Configuración MUST agrupar la programación, la configuración de FlareSolverr y la configuración del token de TMDB. Cada sección SHALL conservar su contrato vigente de validación, precedencia, máscara y protección de escritura.

#### Scenario: Secciones de configuración

- **WHEN** el operador abre `/configuracion`
- **THEN** ve la programación, la URL efectiva de FlareSolverr y el estado del token de TMDB
- **AND** ve los formularios correspondientes si tiene acceso de administración

#### Scenario: Guardado y mensajes

- **WHEN** el operador guarda una sección con éxito o error
- **THEN** vuelve a `/configuracion`
- **AND** ve el mensaje correspondiente en esa página

#### Scenario: Contratos conservados

- **WHEN** el operador guarda o borra la configuración de FlareSolverr, TMDB o la programación
- **THEN** se aplican las mismas reglas de validación, precedencia y protección que antes del cambio
- **AND** los trabajos, las ediciones y el índice permanecen intactos

## MODIFIED Requirements

### Requirement: Actualización automática

El sistema SHALL refrescar automáticamente las páginas de Inicio y Tareas con un intervalo configurable, sin requerir que el operador las recargue manualmente. La página de Configuración SHALL NOT refrescarse automáticamente para no perder cambios en los formularios.

#### Scenario: Refresco periódico

- **WHEN** transcurre el intervalo de refresco configurado
- **THEN** la vista actualiza los datos mostrados
- **AND** el intervalo puede cambiarse mediante configuración de entorno

#### Scenario: Configuración sin refresco

- **WHEN** el operador está editando un formulario en Configuración
- **THEN** la página no se recarga automáticamente
- **AND** los valores introducidos no se pierden por el refresco
