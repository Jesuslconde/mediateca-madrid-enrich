# ingesta-catalogo Specification

## Purpose
Obtener de forma reproducible los registros de vídeos y DVD del OPAC AbsysNet de la Comunidad de Madrid, conservando el HTML original y los metadatos necesarios para reconstruir el índice sin volver a scrapear.

## Requirements

### Requirement: Gestión de sesión del OPAC

El recolector MUST iniciar una sesión válida contra el OPAC, conservar cookies y extraer el identificador de sesión de la ruta antes de consultar resultados o fichas.

#### Scenario: Renovación de sesión caducada

- **WHEN** una petición devuelve la página de sesión expirada o un error de sesión
- **THEN** el recolector renueva la sesión y reintenta la petición una vez
- **AND** registra el evento sin abortar el lote completo

### Requirement: Búsqueda por formato vídeo

El recolector SHALL consultar el formulario avanzado con el filtro de formato `Videos y DVD` y SHALL recorrer la paginación de resultados hasta el límite configurado.

#### Scenario: Recolección de una consulta

- **WHEN** se ejecuta una recolección con una consulta y un límite de páginas
- **THEN** se obtienen las fichas de detalle de los resultados
- **AND** se registra el número de registros procesados y los errores

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

### Requirement: Actualización incremental

El sistema SHALL soportar descubrimientos incrementales reutilizando el `cursor_doc` y `cursor_titn` del último descubrimiento completado, y SHALL programar un barrido completo periódico como red de seguridad.

#### Scenario: Novedades de vídeos

- **WHEN** se ejecuta la recolección incremental
- **THEN** solo se procesan los registros nuevos o modificados del periodo configurado
- **AND** el resto del catálogo permanece intacto

#### Scenario: Sin descubrimiento previo

- **WHEN** se solicita un descubrimiento incremental y no hay un descubrimiento completado
- **THEN** se ejecuta un descubrimiento completo
- **AND** queda registrado como modo `full`

#### Scenario: Barrido completo de seguridad

- **WHEN** se cumple el intervalo de barrido completo
- **THEN** se ejecuta un descubrimiento completo aunque exista un cursor incremental
- **AND** se actualizan las marcas de última visualización y las ausencias

### Requirement: Recolección sin estado de préstamo

El recolector MUST guardar la lista de bibliotecas y sucursales que poseen cada edición al crear o actualizar la ficha, y SHALL NOT consultar ni persistir el estado de préstamo de los ejemplares.

#### Scenario: Ficha procesada

- **WHEN** el recolector procesa la ficha de un activo
- **THEN** guarda sus ejemplares con biblioteca, sucursal, signatura, tipo y soporte
- **AND** no intenta determinar si cada ejemplar está prestado o disponible

#### Scenario: Actualización periódica

- **WHEN** se ejecuta una recolección periódica de fichas
- **THEN** se actualizan los metadatos y la lista de bibliotecas tenedoras
- **AND** no se ejecuta ninguna comprobación de disponibilidad de préstamo

#### Scenario: Ficha sin ejemplares

- **WHEN** la ficha no declara ejemplares
- **THEN** la edición se guarda sin bibliotecas tenedoras
- **AND** la recolección continúa sin error

### Requirement: Descubrimiento completo por truncamiento

El recolector MUST usar la consulta de truncamiento `*` con el filtro de formato `Videos y DVD` y SHALL recorrer toda la paginación hasta agotar los resultados.

#### Scenario: Catálogo completo

- **WHEN** se ejecuta el descubrimiento completo
- **THEN** se recorren todas las páginas de resultados
- **AND** se obtiene el conjunto de `TITN` de vídeo, DVD, Blu-ray, 4K UHD y VHS

#### Scenario: Orden estable

- **WHEN** el OPAC devuelve los resultados de `*`
- **THEN** el orden es `TITN` ascendente
- **AND** la paginación por `DOC` permite reanudar sin pérdidas

### Requirement: Parser de listado de resultados

El recolector MUST extraer de cada resultado el `TITN`, título, publicación, año, idioma, descripción física, géneros, materias y, cuando existan, autores y notas del MARC oculto.

#### Scenario: Resultado con MARC oculto

- **WHEN** se parsea un `li.c-docs_unit`
- **THEN** se obtiene al menos `TITN`, título y descripción física
- **AND** se detecta el soporte desde `T300a`

### Requirement: Checkpoint de descubrimiento

El descubrimiento MUST guardar el último `DOC` y el último `TITN` procesados y SHALL reanudar desde ese punto tras una interrupción.

#### Scenario: Reanudar tras fallo

- **WHEN** el descubrimiento se interrumpe en el registro 20.000
- **THEN** el siguiente trabajo empieza en el `DOC` guardado
- **AND** verifica que el primer `TITN` coincide con el cursor

### Requirement: Sesión durante paginación

Si la sesión caduca durante el descubrimiento, el recolector MUST reabrir sesión, repetir la búsqueda `*` y saltar al `DOC` actual.

#### Scenario: Sesión caducada en página profunda

- **WHEN** el OPAC devuelve la página de sesión expirada en `DOC=40001`
- **THEN** el cliente reabre sesión
- **AND** repite la búsqueda y continúa en el mismo `DOC`

### Requirement: Detección de altas y bajas

El descubrimiento SHALL marcar la fecha de última visualización de cada edición y SHALL identificar los `TITN` que han dejado de aparecer.

#### Scenario: Título nuevo

- **WHEN** aparece un `TITN` que no existía
- **THEN** se crea una edición stub
- **AND** queda pendiente de enriquecimiento

#### Scenario: Título desaparecido

- **WHEN** un `TITN` no aparece en un descubrimiento completo
- **THEN** se marca como no visto
- **AND** no se elimina automáticamente sin revisión

### Requirement: Enriquecimiento completo por lotes

El sistema MUST enriquecer todas las ediciones descubiertas en lotes de 5.000 por defecto, actualizando metadatos, créditos, materias y ejemplares.

#### Scenario: Lote de 5.000 fichas

- **WHEN** se ejecuta un trabajo de enriquecimiento
- **THEN** selecciona hasta 5.000 TITN pendientes
- **AND** al terminar el lote actualiza el cursor y las estadísticas

#### Scenario: Cobertura completa

- **WHEN** no quedan TITN con `detail_fetched_at` vacío
- **THEN** el trabajo termina y la cobertura de enriquecimiento es del 100%
- **AND** se registra en el estado de ingesta

### Requirement: Solo datos parseados

El enriquecimiento MUST persistir únicamente datos normalizados en PostgreSQL y MUST NOT guardar HTML crudo ni snapshots.

#### Scenario: Ficha procesada

- **WHEN** se enriquece un TITN
- **THEN** se guardan sus campos, personas, materias, enlaces y ejemplares
- **AND** no se crea ningún archivo de snapshot

### Requirement: Reanudación por TITN

El enriquecimiento MUST guardar el último `TITN` procesado y SHALL reanudar desde el siguiente pendiente tras un fallo.

#### Scenario: Reinicio del worker

- **WHEN** el worker se reinicia a mitad de un lote
- **THEN** el siguiente trabajo continúa desde el último `TITN` persistido
- **AND** no repite las fichas ya marcadas con `detail_fetched_at`

### Requirement: Errores y reintentos

Una ficha fallida MUST registrarse, reintentarse hasta el máximo configurado y SHALL excluirse del lote activo tras agotar los intentos.

#### Scenario: Ficha con error persistente

- **WHEN** una ficha falla tres veces
- **THEN** se marca con error y no bloquea el resto del lote
- **AND** queda visible para revisión manual

### Requirement: Actualización idempotente de ejemplares

Repetir el enriquecimiento de un TITN MUST actualizar sus ejemplares existentes por `external_key` sin duplicarlos.

#### Scenario: Reenriquecer una edición

- **WHEN** se procesa de nuevo un TITN ya enriquecido
- **THEN** se actualizan sus ejemplares y relaciones
- **AND** no se crean duplicados

### Requirement: Enriquecimiento de registros nuevos

El enriquecimiento programado MUST poder limitarse a las ediciones descubiertas desde un instante `since` y SHALL conservar el resto de pendientes para ejecuciones manuales.

#### Scenario: Solo nuevos

- **WHEN** un enriquecimiento recibe un `since`
- **THEN** selecciona solo ediciones con `discovery_seen_at` mayor o igual que `since` y sin `detail_fetched_at`
- **AND** no procesa stubs anteriores

#### Scenario: Enriquecimiento manual completo

- **WHEN** el operador lanza "Enriquecer pendientes" desde el dashboard
- **THEN** se seleccionan todos los stubs pendientes, sin filtro `since`
- **AND** se respeta el límite de lote configurado
