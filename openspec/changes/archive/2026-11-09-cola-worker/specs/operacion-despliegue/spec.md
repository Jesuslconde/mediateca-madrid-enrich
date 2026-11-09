# operacion-despliegue Specification

## ADDED Requirements

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
