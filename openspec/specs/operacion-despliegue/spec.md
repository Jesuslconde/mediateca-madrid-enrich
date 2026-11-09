# operacion-despliegue Specification

## Purpose
Permitir que cualquier persona levante el portal completo en local o en un servidor con un único comando, con configuración por variables de entorno y verificaciones de salud.

## Requirements

### Requirement: Despliegue con Docker Compose

El proyecto MUST incluir un `docker-compose.yml` con PostgreSQL, Meilisearch, API, scheduler y frontend, con volúmenes persistentes para base de datos, índice y snapshots.

#### Scenario: Arranque completo

- **WHEN** se ejecuta `docker compose up --build`
- **THEN** los servicios arrancan en el orden de dependencia
- **AND** la API y el portal quedan accesibles por sus puertos

### Requirement: Configuración por entorno

Todas las credenciales y URLs MUST configurarse mediante variables de entorno y SHALL existir un `.env.example` documentado.

#### Scenario: Cambio de clave de Meilisearch

- **WHEN** se cambia `MEILI_MASTER_KEY` en el entorno
- **THEN** API e indexador usan la nueva clave
- **AND** no se requiere modificar código

### Requirement: Inicialización de base de datos

El backend MUST ofrecer un comando idempotente para crear el esquema y los índices de búsqueda.

#### Scenario: Primer arranque

- **WHEN** se ejecuta el comando de inicialización
- **THEN** se crean las tablas y el índice de Meilisearch si no existen
- **AND** puede ejecutarse de nuevo sin errores

### Requirement: Healthchecks

Los servicios críticos MUST declarar healthchecks y SHALL exponer un endpoint de salud agregado.

#### Scenario: Servicio caído

- **WHEN** PostgreSQL no responde
- **THEN** `/health` devuelve estado degradado
- **AND** Docker muestra el servicio como unhealthy

### Requirement: Verificación y documentación

El repositorio MUST incluir un README con los comandos de arranque, ingesta, indexación y pruebas, y SHALL incluir un Makefile con los atajos principales.

#### Scenario: Nuevo desarrollador

- **WHEN** una persona clona el repositorio y sigue el README
- **THEN** puede levantar el portal y ejecutar una ingesta de prueba
- **AND** puede ejecutar las pruebas del parser y del filtro de soporte

### Requirement: Servicio worker en Docker Compose

El despliegue MUST incluir un servicio `worker` construido con la misma imagen que la API y SHALL compartir base de datos, Meilisearch y variables de entorno.

#### Scenario: Arranque del worker

- **WHEN** se ejecuta `docker compose up -d`
- **THEN** el servicio `worker` arranca con la misma imagen del backend
- **AND** queda conectado a PostgreSQL y Meilisearch

### Requirement: Healthcheck del worker

El worker MUST exponer una señal de salud o escribir un heartbeat verificable y SHALL marcarse como unhealthy si deja de procesar durante el tiempo configurado.

#### Scenario: Worker sin heartbeat

- **WHEN** el worker deja de actualizar su heartbeat
- **THEN** Docker lo marca como unhealthy
- **AND** el operador puede reiniciarlo sin perder el cursor del trabajo

### Requirement: Servicio dashboard en Docker Compose

El despliegue MUST incluir un servicio `dashboard` construido con la misma imagen que el worker y SHALL publicar su puerto configurable para servir la vista de estado.

#### Scenario: Arranque del dashboard

- **WHEN** se ejecuta `docker compose up -d`
- **THEN** el servicio `dashboard` arranca con la misma imagen del worker
- **AND** la vista queda accesible en el puerto configurado
- **AND** el servicio se conecta a PostgreSQL para leer el estado

#### Scenario: Puerto configurable

- **WHEN** se cambia la variable de entorno del puerto del dashboard
- **THEN** el servicio publica el nuevo puerto
- **AND** no se requiere modificar código

### Requirement: Healthcheck del dashboard

El dashboard MUST declarar un healthcheck y SHALL exponer una ruta de salud que verifique que la aplicación responde.

#### Scenario: Dashboard sin respuesta

- **WHEN** la aplicación del dashboard deja de responder
- **THEN** Docker lo marca como unhealthy
- **AND** el operador puede reiniciarlo sin afectar al worker ni a la ingesta
