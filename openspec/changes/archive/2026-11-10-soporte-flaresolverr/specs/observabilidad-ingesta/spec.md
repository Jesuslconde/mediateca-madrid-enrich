# Spec Delta

## MODIFIED Requirements

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
