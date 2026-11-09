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

### Requirement: Persistencia de snapshots

Cada ficha descargada MUST guardarse como snapshot inmutable con su URL, fecha de captura y hash, de forma que el parseo pueda repetirse sin nueva descarga.

#### Scenario: Reproceso sin red

- **WHEN** se ejecuta el parseo sobre snapshots existentes
- **THEN** no se realizan peticiones al OPAC
- **AND** se generan los mismos registros normalizados

### Requirement: Límite de peticiones y reintentos

El recolector MUST aplicar un retardo configurable entre peticiones y MUST reintentar con backoff los errores temporales, sin intentar eludir reCAPTCHA ni mecanismos de protección.

#### Scenario: Error temporal del servidor

- **WHEN** el OPAC responde con un error 5xx o un timeout
- **THEN** la petición se reintenta hasta el máximo configurado
- **AND** si persiste, la ficha se envía a una cola de fallidos

### Requirement: Actualización incremental

El sistema SHALL soportar recolecciones incrementales mediante las consultas de novedades o un conjunto de consultas configurado.

#### Scenario: Novedades de vídeos

- **WHEN** se ejecuta la recolección incremental
- **THEN** solo se procesan los registros nuevos o modificados del periodo configurado
- **AND** el resto del catálogo permanece intacto

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
