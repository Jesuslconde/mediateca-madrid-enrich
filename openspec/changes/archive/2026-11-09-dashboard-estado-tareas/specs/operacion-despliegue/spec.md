# Spec Delta

## ADDED Requirements

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
