# Spec Delta

## Purpose

Ofrecer al operador una vista web pequeña y de solo lectura para conocer el estado de los trabajos de ingesta, la cobertura del catálogo y la salud del worker sin consultar PostgreSQL ni ejecutar comandos.

## ADDED Requirements

### Requirement: Vista web de solo lectura

El sistema MUST exponer una página web que muestre el estado de los trabajos de ingesta y la cobertura del catálogo, y MUST limitarse a operaciones de lectura.

#### Scenario: Acceso a la vista

- **WHEN** el operador abre la URL del dashboard
- **THEN** recibe una página HTML con el estado de los trabajos y la cobertura
- **AND** la carga no crea, modifica ni elimina trabajos, ediciones ni entradas del índice

#### Scenario: Refresco sin efectos secundarios

- **WHEN** el operador recarga la página varias veces
- **THEN** la vista vuelve a leer el estado actual
- **AND** no se ejecuta ninguna escritura en la base de datos

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
