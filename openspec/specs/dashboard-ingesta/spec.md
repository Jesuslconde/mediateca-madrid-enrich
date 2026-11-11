# dashboard-ingesta Specification

## Purpose

Ofrecer al operador una vista web pequeña y de solo lectura para conocer el estado de los trabajos de ingesta, la cobertura del catálogo y la salud del worker sin consultar PostgreSQL ni ejecutar comandos.

## Requirements

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

### Requirement: Configuración de FlareSolverr desde el dashboard

El dashboard MUST mostrar y permitir guardar la URL de FlareSolverr. La URL guardada SHALL prevalecer sobre `MEDIATECA_FLARESOLVERR_URL`; si no hay valor guardado, se usa la variable de entorno. El sistema MUST validar que sea una URL HTTP o HTTPS y SHALL rechazar valores inválidos sin cambiar la configuración vigente.

#### Scenario: Mostrar configuración vigente

- **WHEN** el operador abre el dashboard
- **THEN** ve la URL efectiva de FlareSolverr o un campo vacío si no está configurada
- **AND** ve si el origen es la configuración del dashboard, la variable de entorno o ninguno
- **AND** ve si la resolución de captchas está activa

#### Scenario: Guardar una URL válida

- **WHEN** el operador envía una URL HTTP o HTTPS válida
- **THEN** la configuración se persiste en PostgreSQL
- **AND** los trabajos de ingesta lanzados después usan esa URL
- **AND** el dashboard muestra el nuevo valor y su origen

#### Scenario: Limpiar la configuración

- **WHEN** el operador guarda el campo vacío
- **THEN** se elimina la URL persistida
- **AND** se usa la variable de entorno si existe
- **AND** si tampoco existe, la resolución de captchas queda desactivada

#### Scenario: URL inválida

- **WHEN** el operador envía un valor que no es una URL HTTP o HTTPS
- **THEN** el dashboard muestra un error comprensible
- **AND** no se modifica la configuración vigente

#### Scenario: Error al persistir

- **WHEN** la base de datos no permite guardar la configuración
- **THEN** el dashboard muestra un error comprensible
- **AND** no deja la configuración a medio actualizar

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

### Requirement: Resumen de trabajos por estado y tipo

El sistema MUST mostrar el número de trabajos agrupados por estado (`pending`, `running`, `completed`, `failed`, `cancelled`) y por tipo (`discover`, `enrich`, `index`).

#### Scenario: Conteo por estado

- **WHEN** existen trabajos en varios estados
- **THEN** la vista muestra el total de cada estado
- **AND** los estados sin trabajos se muestran con valor cero

#### Scenario: Conteo por tipo

- **WHEN** existen trabajos de descubrimiento, enriquecimiento e indexación
- **THEN** la vista muestra el total de cada tipo
- **AND** los tipos sin trabajos se muestran con valor cero

### Requirement: Detalle de trabajos recientes

El sistema MUST listar los trabajos más recientes ordenados por fecha de creación descendente, con identificador, tipo, estado, cursor, intentos, fechas de inicio y fin, heartbeat y error.

#### Scenario: Trabajo fallido visible

- **WHEN** un trabajo termina en estado `failed`
- **THEN** la vista muestra su error y el número de intentos realizados
- **AND** el trabajo aparece entre los más recientes

#### Scenario: Límite de trabajos mostrados

- **WHEN** hay más trabajos que el límite configurado
- **THEN** la vista muestra solo los más recientes
- **AND** el resumen por estado sigue contando todos los trabajos

### Requirement: Cobertura del catálogo

El sistema SHALL mostrar el número de ediciones descubiertas, enriquecidas, pendientes y fallidas, junto con el porcentaje de enriquecimiento sobre el total.

#### Scenario: Cobertura parcial

- **WHEN** se han enriquecido parte de las ediciones del catálogo
- **THEN** la vista muestra los conteos y el porcentaje de enriquecimiento
- **AND** el número de pendientes coincide con las ediciones sin enriquecer

#### Scenario: Catálogo vacío

- **WHEN** no existen ediciones
- **THEN** la vista muestra cero en todas las métricas
- **AND** el porcentaje de enriquecimiento se muestra como cero sin dividir por cero

### Requirement: Salud del worker

El sistema MUST mostrar el último heartbeat del worker y SHALL marcar el estado como `degraded` cuando el heartbeat supere el umbral configurado.

#### Scenario: Worker activo

- **WHEN** el heartbeat es reciente
- **THEN** la vista muestra el estado del worker como `ok`
- **AND** muestra la fecha del último heartbeat

#### Scenario: Worker detenido

- **WHEN** el heartbeat supera el umbral configurado o no existe
- **THEN** la vista muestra el estado del worker como `degraded`
- **AND** el resto de métricas y trabajos sigue visible

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

### Requirement: Tolerancia a fallos de la base de datos

El sistema MUST responder con un estado de error comprensible cuando la base de datos no está disponible, sin exponer trazas internas ni caerse.

#### Scenario: Base de datos no disponible

- **WHEN** la base de datos no responde
- **THEN** la vista devuelve un estado `degraded` con un mensaje comprensible
- **AND** no muestra trazas de pila ni detalles de conexión

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
