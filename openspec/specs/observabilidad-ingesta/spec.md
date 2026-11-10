# observabilidad-ingesta Specification

## Purpose

Permitir que el operador sepa en todo momento qué está haciendo la ingesta, qué ha completado, qué falta, qué ha fallado y cuánto está tardando.

## Requirements

### Requirement: Estado de ingesta

El sistema MUST exponer el estado de los trabajos activos, completados y fallidos, con tipo, cursor, intentos, inicio, fin y estadísticas.

#### Scenario: Consulta de trabajos

- **WHEN** el operador consulta el estado
- **THEN** ve los trabajos ordenados por fecha
- **AND** puede distinguir `pending`, `running`, `completed` y `failed`

### Requirement: Cobertura del catálogo

El sistema MUST exponer el número de ediciones descubiertas, enriquecidas, pendientes, fallidas y desaparecidas.

#### Scenario: Cobertura al 50%

- **WHEN** se han enriquecido 33.600 de 67.215 ediciones
- **THEN** la cobertura muestra el 50%
- **AND** el número de pendientes coincide con la cola

### Requirement: Métricas de ingesta

El sistema SHALL registrar y exponer métricas de fichas procesadas, errores, captchas detectados, captchas resueltos, captchas fallidos, renovaciones de sesión y tiempo medio por ficha.

#### Scenario: Errores y captcha

- **WHEN** una ejecución encuentra un reCAPTCHA
- **THEN** incrementa el contador de captchas detectados
- **AND** incrementa el contador de captchas resueltos o fallidos según el resultado
- **AND** el trabajo continúa o se reprograma según la política

#### Scenario: Captcha resuelto

- **WHEN** una ejecución detecta un reCAPTCHA y FlareSolverr lo resuelve
- **THEN** incrementa el contador de captchas detectados
- **AND** incrementa el contador de captchas resueltos
- **AND** la ficha se procesa con la respuesta resuelta

#### Scenario: Captcha no resuelto

- **WHEN** una ejecución detecta un reCAPTCHA y no hay FlareSolverr configurado o la resolución falla
- **THEN** incrementa el contador de captchas detectados
- **AND** incrementa el contador de captchas fallidos
- **AND** el trabajo se detiene o se reprograma según la política

#### Scenario: Consulta de métricas

- **WHEN** el operador consulta el estado de ingesta por API, CLI o dashboard
- **THEN** ve los captchas detectados, resueltos y fallidos
- **AND** los contadores se agregan a partir de las estadísticas persistidas de los trabajos

### Requirement: Logs estructurados

Los logs de ingesta MUST incluir `job_id`, `job_type`, `titn`, `doc`, `result` y `duration_ms` en formato estructurado.

#### Scenario: Ficha fallida

- **WHEN** una ficha no se puede procesar
- **THEN** el log incluye el `TITN`, el error y el número de intento
- **AND** no se registra información personal

### Requirement: Salud del worker

El sistema MUST exponer el último heartbeat del worker y SHALL marcar la ingesta como degradada si no hay heartbeat reciente.

#### Scenario: Worker detenido

- **WHEN** el worker lleva más de dos minutos sin heartbeat
- **THEN** el estado de ingesta muestra `degraded`
- **AND** el operador puede reiniciar el worker sin perder el cursor
