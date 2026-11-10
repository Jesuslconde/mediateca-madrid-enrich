# Spec Delta

## MODIFIED Requirements

### Requirement: Vista web de solo lectura

El sistema MUST exponer una página web que muestre el estado de los trabajos de ingesta y la cobertura del catálogo, y MUST limitar las escrituras a la configuración y al encolado de trabajos.

#### Scenario: Acceso a la vista

- **WHEN** el operador abre la URL del dashboard
- **THEN** recibe una página HTML con el estado de los trabajos y la cobertura
- **AND** la carga no crea, modifica ni elimina trabajos, ediciones ni entradas del índice

#### Scenario: Refresco sin efectos secundarios

- **WHEN** el operador recarga la página varias veces
- **THEN** la vista vuelve a leer el estado actual
- **AND** no se ejecuta ninguna escritura salvo que el operador envíe un formulario de configuración o de encolado

#### Scenario: Escritura de configuración explícita

- **WHEN** el operador guarda la configuración de FlareSolverr o de la programación
- **THEN** solo se escribe esa configuración
- **AND** los trabajos, las ediciones y el índice permanecen intactos

#### Scenario: Encolado explícito de trabajos

- **WHEN** el operador pulsa una acción de tareas bajo demanda
- **THEN** se crea como máximo un trabajo `pending` del tipo solicitado
- **AND** no se ejecuta la ingesta dentro del proceso del dashboard

## ADDED Requirements

### Requirement: Tareas bajo demanda

El dashboard MUST permitir encolar descubrimiento incremental, descubrimiento completo, enriquecimiento e indexación, y SHALL rechazar la acción si ya existe un trabajo activo del mismo tipo.

#### Scenario: Buscar novedades

- **WHEN** el operador pulsa "Buscar novedades"
- **THEN** se encola un `discover` incremental con el cursor del último descubrimiento completado
- **AND** el worker lo procesa cuando esté libre

#### Scenario: Enriquecer pendientes

- **WHEN** el operador pulsa "Enriquecer pendientes"
- **THEN** se encola un `enrich` con el lote indicado
- **AND** se procesan todos los stubs pendientes, no solo los de la última búsqueda

#### Scenario: Trabajo duplicado

- **WHEN** ya hay un trabajo `pending` o `running` del mismo tipo
- **THEN** el dashboard muestra un error comprensible
- **AND** no crea otro trabajo

### Requirement: Programación configurable

El dashboard MUST mostrar y permitir guardar la activación, los intervalos de descubrimiento, barrido completo y enriquecimiento, y el tamaño de lote. La configuración SHALL persistirse en `app_config` y ser usada por el scheduler sin reiniciar.

#### Scenario: Mostrar programación

- **WHEN** el operador abre el dashboard
- **THEN** ve el estado de la programación, la última y la próxima ejecución
- **AND** ve los trabajos activos por tipo y los pendientes de enriquecer

#### Scenario: Guardar intervalos válidos

- **WHEN** el operador guarda intervalos y lote válidos
- **THEN** la configuración se persiste y el scheduler la aplica en la siguiente comprobación
- **AND** el dashboard muestra los nuevos valores

#### Scenario: Valor inválido

- **WHEN** el operador envía un intervalo o lote fuera de rango
- **THEN** el dashboard muestra un error
- **AND** no modifica la configuración vigente

### Requirement: Token de escritura del dashboard

El sistema MUST exigir un token para las acciones de escritura del dashboard cuando `MEDIATECA_DASHBOARD_ADMIN_TOKEN` esté configurado, y SHALL permitir la lectura sin token.

#### Scenario: Escritura sin token

- **WHEN** un operador intenta guardar configuración o encolar un trabajo sin token válido
- **THEN** la escritura se rechaza con un mensaje comprensible
- **AND** no se modifica la base de datos

#### Scenario: Login correcto

- **WHEN** el operador introduce el token correcto
- **THEN** se guarda una cookie de administración `HttpOnly` y `SameSite=Strict`
- **AND** puede usar los formularios de escritura durante la sesión
