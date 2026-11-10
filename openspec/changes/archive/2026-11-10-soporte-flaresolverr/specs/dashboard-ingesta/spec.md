# Spec Delta

## MODIFIED Requirements

### Requirement: Vista web de solo lectura

El sistema MUST exponer una página web que muestre el estado de los trabajos de ingesta y la cobertura del catálogo, y MUST limitar las escrituras a la configuración de FlareSolverr.

#### Scenario: Acceso a la vista

- **WHEN** el operador abre la URL del dashboard
- **THEN** recibe una página HTML con el estado de los trabajos y la cobertura
- **AND** la carga no crea, modifica ni elimina trabajos, ediciones ni entradas del índice

#### Scenario: Refresco sin efectos secundarios

- **WHEN** el operador recarga la página varias veces
- **THEN** la vista vuelve a leer el estado actual
- **AND** no se ejecuta ninguna escritura salvo que el operador envíe el formulario de configuración

#### Scenario: Escritura de configuración explícita

- **WHEN** el operador guarda la configuración de FlareSolverr
- **THEN** solo se escribe esa configuración
- **AND** los trabajos, las ediciones y el índice permanecen intactos

## ADDED Requirements

### Requirement: Configuración de FlareSolverr desde el dashboard

El dashboard MUST mostrar y permitir guardar la URL de FlareSolverr. La URL guardada SHALL prevalecer sobre `MEDIATECA_FLARESOLVERR_URL`; si no hay valor guardado, se usa la variable de entorno. El sistema MUST validar que sea una URL HTTP o HTTPS y SHALL rechazar valores inválidos sin cambiar la configuración vigente.

#### Scenario: Mostrar configuración vigente

- **WHEN** el operador abre el dashboard
- **THEN** ve la URL efectiva de FlareSolverr o un campo vacío si no está configurada
- **AND** ve si el origen es la configuración del dashboard, la variable de entorno o ninguno
- **AND** ve si la resolución de captchas está activa

#### Scenario: Guardar una URL válida

- **WHEN** el operador envía una URL HTTP o HTTPS válida
- **THEN** la configuración se persiste en PostgreSQL
- **AND** los trabajos de ingesta lanzados después usan esa URL
- **AND** el dashboard muestra el nuevo valor y su origen

#### Scenario: Limpiar la configuración

- **WHEN** el operador guarda el campo vacío
- **THEN** se elimina la URL persistida
- **AND** se usa la variable de entorno si existe
- **AND** si tampoco existe, la resolución de captchas queda desactivada

#### Scenario: URL inválida

- **WHEN** el operador envía un valor que no es una URL HTTP o HTTPS
- **THEN** el dashboard muestra un error comprensible
- **AND** no se modifica la configuración vigente

#### Scenario: Error al persistir

- **WHEN** la base de datos no permite guardar la configuración
- **THEN** el dashboard muestra un error comprensible
- **AND** no deja la configuración a medio actualizar
