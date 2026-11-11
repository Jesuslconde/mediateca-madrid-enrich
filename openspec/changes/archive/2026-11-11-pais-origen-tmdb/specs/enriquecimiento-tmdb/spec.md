# Spec Delta

## Purpose

Obtener de TMDB los países de producción de una edición para completar el catálogo con un dato normalizado y fiable, sin sustituir los metadatos del OPAC ni bloquear la ingesta cuando TMDB no esté disponible.

## ADDED Requirements

### Requirement: Consulta opcional a TMDB

El sistema MUST consultar TMDB solo cuando exista un token de API válido configurado en el dashboard o, en su defecto, en el entorno. Si no hay token, SHALL omitir la consulta sin error y SHALL dejar la edición pendiente de enriquecimiento TMDB. El sistema SHALL aceptar una API Key v3 o un Read Access Token v4.

#### Scenario: Token configurado

- **WHEN** existe un token de TMDB configurado y se enriquece una edición
- **THEN** el sistema consulta TMDB para esa edición
- **AND** registra el resultado de la consulta

#### Scenario: Sin token configurado

- **WHEN** no existe un token de TMDB configurado
- **THEN** el enriquecimiento del OPAC termina con éxito
- **AND** la edición no se marca como sincronizada con TMDB
- **AND** no se registra un error por la ausencia de token

#### Scenario: Token guardado en el dashboard

- **WHEN** el operador guarda un token en el dashboard y no existe la variable de entorno
- **THEN** el siguiente trabajo de enriquecimiento o backfill usa ese token
- **AND** el dashboard muestra el origen `dashboard`

#### Scenario: Precedencia del dashboard sobre el entorno

- **WHEN** existen un token guardado en el dashboard y una variable de entorno distinta
- **THEN** se usa el token guardado en el dashboard
- **AND** el token del entorno queda como respaldo si se borra el guardado

#### Scenario: API Key v3

- **WHEN** el token configurado no tiene formato de JWT
- **THEN** el cliente lo envía como API Key v3 de TMDB

#### Scenario: Read Access Token v4

- **WHEN** el token configurado tiene formato de JWT
- **THEN** el cliente lo envía como Read Access Token v4 con `Authorization: Bearer`

#### Scenario: Token guardado inválido

- **WHEN** el token persistido no supera la validación
- **THEN** se ignora y se usa la variable de entorno si existe
- **AND** si tampoco existe, el enriquecimiento TMDB se omite sin error

### Requirement: Emparejamiento por título y año

El sistema MUST localizar la película en TMDB usando el título y el año de la edición y SHALL aceptar un resultado solo cuando el año coincida con una tolerancia máxima de un año. Si no hay un resultado suficientemente fiable, SHALL dejar la edición sin países y sin marcar como sincronizada.

#### Scenario: Coincidencia fiable

- **WHEN** el título normalizado y el año de la edición coinciden con un resultado de TMDB
- **THEN** el sistema selecciona ese resultado
- **AND** conserva el identificador de TMDB de la película

#### Scenario: Sin coincidencia fiable

- **WHEN** ningún resultado de TMDB coincide con el título y el año dentro de la tolerancia
- **THEN** la edición conserva su `pais` del OPAC y una lista `paises_origen` vacía
- **AND** no se marca como sincronizada con TMDB
- **AND** el fallo de emparejamiento queda registrado para revisión

#### Scenario: Título con puntuación del OPAC

- **WHEN** el título del OPAC termina en puntuación o separadores como ` / `
- **THEN** el sistema normaliza el título antes de consultar TMDB
- **AND** la puntuación final no impide la coincidencia

### Requirement: Obtención de países de producción

El sistema MUST obtener los países de producción de la película seleccionada y SHALL persistirlos como una lista de códigos ISO 3166-1 alfa-2 en mayúsculas, sin duplicados y en el orden devuelto por TMDB.

#### Scenario: Película con varios países

- **WHEN** TMDB devuelve los países `ES` y `FR` para una película
- **THEN** la edición guarda `paises_origen: ["ES", "FR"]`

#### Scenario: Película sin países informados

- **WHEN** TMDB no devuelve países de producción para una película emparejada
- **THEN** la edición guarda `paises_origen: []`
- **AND** se marca como sincronizada con TMDB

### Requirement: Idempotencia y conservación del dato del OPAC

Repetir el enriquecimiento TMDB de una edición MUST actualizar `paises_origen`, `tmdb_id` y `tmdb_enriched_at` sin duplicar la edición ni modificar el campo `pais` procedente del OPAC. Un fallo de TMDB SHALL NOT borrar países ya almacenados ni marcar la edición como sincronizada.

#### Scenario: Reenriquecimiento de una edición

- **WHEN** se repite el enriquecimiento TMDB de una edición ya sincronizada
- **THEN** se actualizan sus campos TMDB con el resultado actual
- **AND** no se crea una segunda edición
- **AND** el campo `pais` del OPAC permanece intacto

#### Scenario: Fallo después de una sincronización previa

- **WHEN** una edición ya tenía países de TMDB y una nueva consulta falla
- **THEN** se conservan los países anteriores
- **AND** la edición no se marca con una nueva fecha de sincronización

### Requirement: Tolerancia a fallos y límites de uso

El sistema MUST aplicar un retardo configurable entre peticiones, MUST reintentar los errores temporales con backoff y SHALL respetar el tiempo indicado por TMDB ante un límite de peticiones. Un fallo de TMDB SHALL NOT impedir que la ficha del OPAC se guarde como enriquecida.

#### Scenario: Error temporal de TMDB

- **WHEN** TMDB responde con un error temporal o un timeout
- **THEN** la petición se reintenta hasta el máximo configurado
- **AND** si persiste, el fallo se registra y el enriquecimiento del OPAC continúa

#### Scenario: Límite de peticiones

- **WHEN** TMDB responde con un límite de peticiones y un tiempo de espera
- **THEN** el sistema espera al menos ese tiempo antes de reintentar
- **AND** si se agota el máximo de reintentos, la edición queda pendiente sin invalidar el lote

#### Scenario: Ficha del OPAC ya guardada

- **WHEN** el enriquecimiento del OPAC se ha guardado y la consulta a TMDB falla
- **THEN** la edición sigue marcada como enriquecida por el OPAC
- **AND** queda pendiente para el backfill de TMDB

### Requirement: Backfill manual

El sistema SHALL ofrecer un comando manual que enriquezca con TMDB las ediciones pendientes, por lotes y con reanudación, sin reprocesar las ya sincronizadas.

#### Scenario: Lote de backfill

- **WHEN** el operador ejecuta el backfill con un límite de lote
- **THEN** se procesan hasta ese número de ediciones sin `tmdb_enriched_at`
- **AND** al terminar se informa del número de procesadas, emparejadas, sin coincidencia y fallidas

#### Scenario: Reanudación del backfill

- **WHEN** el backfill se interrumpe a mitad de un lote
- **THEN** la siguiente ejecución continúa por las ediciones que siguen pendientes
- **AND** no repite las ya sincronizadas

#### Scenario: Backfill sin token

- **WHEN** el operador ejecuta el backfill sin un token de TMDB configurado
- **THEN** el comando termina con un error legible
- **AND** no modifica ninguna edición
