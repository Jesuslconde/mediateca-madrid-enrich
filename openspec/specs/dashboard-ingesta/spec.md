# dashboard-ingesta Specification

## Purpose

Ofrecer al operador una vista web pequeña y de solo lectura para conocer el estado de los trabajos de ingesta, la cobertura del catálogo y la salud del worker sin consultar PostgreSQL ni ejecutar comandos.

## Requirements

### Requirement: Vista web de solo lectura

El sistema MUST exponer una página web que muestre el estado de los trabajos de ingesta y la cobertura del catálogo, y MUST limitar las escrituras a la configuración de FlareSolverr.

#### Scenario: Acceso a la vista

- **WHEN** el operador abre la URL del dashboard
- **THEN** recibe una página HTML con el estado de los trabajos y la cobertura
- **AND** la carga no crea, modifica ni elimina trabajos, ediciones ni entradas del índice

#### Scenario: Refresco sin efectos secundarios

- **WHEN** el operador recarga la página varias veces
- **THEN** la vista vuelve a leer el estado actual
- **AND** no se ejecuta ninguna escritura salvo que el operador envíe el formulario de configuración

#### Scenario: Escritura de configuración explícita

- **WHEN** el operador guarda la configuración de FlareSolverr
- **THEN** solo se escribe esa configuración
- **AND** los trabajos, las ediciones y el índice permanecen intactos

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

El sistema SHALL refrescar la página automáticamente con un intervalo configurable, sin requerir que el operador la recargue manualmente.

#### Scenario: Refresco periódico

- **WHEN** transcurre el intervalo de refresco configurado
- **THEN** la vista actualiza los datos mostrados
- **AND** el intervalo puede cambiarse mediante configuración de entorno

### Requirement: Tolerancia a fallos de la base de datos

El sistema MUST responder con un estado de error comprensible cuando la base de datos no está disponible, sin exponer trazas internas ni caerse.

#### Scenario: Base de datos no disponible

- **WHEN** la base de datos no responde
- **THEN** la vista devuelve un estado `degraded` con un mensaje comprensible
- **AND** no muestra trazas de pila ni detalles de conexión
