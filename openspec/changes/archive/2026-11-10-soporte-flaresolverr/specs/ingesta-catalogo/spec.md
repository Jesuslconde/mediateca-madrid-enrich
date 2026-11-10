# Spec Delta

## MODIFIED Requirements

### Requirement: Límite de peticiones y reintentos

El recolector MUST aplicar un retardo configurable entre peticiones y MUST reintentar con backoff los errores temporales.

#### Scenario: Error temporal del servidor

- **WHEN** el OPAC responde con un error 5xx o un timeout
- **THEN** la petición se reintenta hasta el máximo configurado
- **AND** si persiste, la ficha se envía a una cola de fallidos

#### Scenario: Captcha sin FlareSolverr configurado

- **WHEN** el OPAC solicita un reCAPTCHA y no existe una URL efectiva de FlareSolverr
- **THEN** el recolector registra el captcha y detiene la petición
- **AND** el trabajo se reprograma según la política de reintentos existente
- **AND** no se intenta resolver el captcha por ningún otro medio

#### Scenario: Captcha con FlareSolverr no disponible

- **WHEN** el OPAC solicita un reCAPTCHA y FlareSolverr no responde o devuelve un error
- **THEN** el recolector registra el captcha fallido y detiene la petición
- **AND** el trabajo se reprograma con backoff
- **AND** no se repite la resolución del mismo captcha dentro de la misma petición

## ADDED Requirements

### Requirement: Resolución de captcha con FlareSolverr

El recolector MUST detectar la página de reCAPTCHA y, cuando exista una URL efectiva de FlareSolverr, resolver la misma petición a través de FlareSolverr y continuar con la respuesta obtenida. Si la resolución falla, MUST registrar el fallo y SHALL NOT entrar en un bucle de reintentos de captcha.

#### Scenario: Petición GET resuelta

- **WHEN** una petición GET recibe la página de reCAPTCHA y FlareSolverr está configurado
- **THEN** el recolector envía a FlareSolverr la misma URL, método y cookies de sesión
- **AND** usa el HTML y la URL final devueltos como respuesta de la petición
- **AND** continúa la recolección sin contar la petición como fallida

#### Scenario: Búsqueda POST resuelta

- **WHEN** la búsqueda del OPAC recibe un reCAPTCHA y FlareSolverr está configurado
- **THEN** el recolector envía a FlareSolverr el mismo método POST y los mismos datos de formulario
- **AND** conserva la sesión y los parámetros de búsqueda originales

#### Scenario: Cookies devueltas por FlareSolverr

- **WHEN** FlareSolverr resuelve una petición y devuelve cookies
- **THEN** el recolector incorpora esas cookies a su sesión del OPAC
- **AND** las peticiones posteriores las usan
- **AND** la paginación y el identificador de sesión siguen siendo válidos

#### Scenario: Respuesta que sigue siendo captcha

- **WHEN** la respuesta devuelta por FlareSolverr vuelve a contener el reCAPTCHA
- **THEN** el recolector la trata como resolución fallida
- **AND** no vuelve a invocar a FlareSolverr para esa misma petición
- **AND** registra el fallo para la política de reintentos del trabajo
