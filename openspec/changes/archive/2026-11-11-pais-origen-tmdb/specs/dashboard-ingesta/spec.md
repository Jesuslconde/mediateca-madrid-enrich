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

- **WHEN** el operador guarda la configuración de FlareSolverr, de TMDB o de la programación
- **THEN** solo se escribe esa configuración
- **AND** los trabajos, las ediciones y el índice permanecen intactos

#### Scenario: Encolado explícito de trabajos

- **WHEN** el operador pulsa una acción de tareas bajo demanda
- **THEN** se crea como máximo un trabajo `pending` del tipo solicitado
- **AND** no se ejecuta la ingesta dentro del proceso del dashboard

## ADDED Requirements

### Requirement: Configuración del token de TMDB desde el dashboard

El dashboard MUST mostrar y permitir guardar o borrar el token de API de TMDB. El token guardado SHALL persistirse en `app_config` y prevalecer sobre `MEDIATECA_TMDB_API_TOKEN`; si no hay valor guardado, se usa la variable de entorno. El sistema MUST validar el token y SHALL rechazar valores inválidos sin cambiar la configuración vigente.

#### Scenario: Mostrar configuración vigente

- **WHEN** el operador abre el dashboard
- **THEN** ve si hay token de TMDB configurado y su origen (`dashboard`, `entorno` o `ninguno`)
- **AND** ve solo una versión enmascarada del token, nunca el valor completo
- **AND** ve si el enriquecimiento TMDB está activo o inactivo

#### Scenario: Guardar un token válido

- **WHEN** el operador envía un token válido
- **THEN** el token se persiste en `app_config`
- **AND** los trabajos de enriquecimiento y backfill lanzados después lo usan
- **AND** el dashboard muestra el nuevo origen y la versión enmascarada

#### Scenario: Campo vacío conserva el token

- **WHEN** el operador guarda el formulario con el campo vacío y sin marcar la opción de borrado
- **THEN** se conserva el token guardado
- **AND** no se usa la variable de entorno mientras exista ese token

#### Scenario: Borrar el token

- **WHEN** el operador marca la opción de borrado y guarda
- **THEN** se elimina el token persistido
- **AND** se usa la variable de entorno si existe
- **AND** si tampoco existe, el enriquecimiento TMDB queda desactivado

#### Scenario: Token inválido

- **WHEN** el operador envía un valor con espacios, caracteres de control o una longitud fuera del rango admitido
- **THEN** el dashboard muestra un error comprensible
- **AND** no se modifica la configuración vigente

#### Scenario: Error al persistir

- **WHEN** la base de datos no permite guardar la configuración
- **THEN** el dashboard muestra un error comprensible
- **AND** no deja la configuración a medio actualizar

### Requirement: Protección del token de TMDB

El sistema MUST NOT mostrar el token completo en la interfaz ni registrarlo en logs o mensajes de error. Las acciones de escritura del token SHALL requerir el token de administración cuando `MEDIATECA_DASHBOARD_ADMIN_TOKEN` esté configurado.

#### Scenario: Token no expuesto en la vista

- **WHEN** el dashboard muestra la configuración de TMDB
- **THEN** el HTML no contiene el token completo
- **AND** solo muestra un identificador enmascarado

#### Scenario: Token no registrado en logs

- **WHEN** se guarda, valida o usa el token
- **THEN** los logs no incluyen el valor del token
- **AND** los errores tampoco lo incluyen

#### Scenario: Escritura sin administración

- **WHEN** un operador sin token de administración intenta guardar o borrar el token de TMDB
- **THEN** la escritura se rechaza con un mensaje comprensible
- **AND** no se modifica la base de datos
