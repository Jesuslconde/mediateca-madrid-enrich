# Proposal

## Why

El dashboard concentra en una sola página los estados, la tabla de trabajos, las acciones de encolado y tres bloques de configuración. A medida que crecen la ingesta y las integraciones externas, la página de inicio se vuelve larga y mezcla consulta con administración. Separar estados, tareas y configuración en páginas con un menú lateral hace la vista más clara y reduce el riesgo de tocar configuración al revisar el estado.

## What Changes

- Dividir el dashboard en tres páginas: Inicio (`/`) para estados, Tareas (`/tareas`) para trabajos y acciones, y Configuración (`/configuracion`) para ajustes.
- Mantener en Inicio solo la salud del worker, el resumen de trabajos por estado y tipo, la cobertura del catálogo y las métricas de ingesta.
- Mover a Tareas la tabla de trabajos recientes y las acciones de descubrimiento, enriquecimiento e indexación.
- Mover a Configuración la programación, la URL de FlareSolverr y el token de TMDB, conservando la validación, la precedencia y la protección actuales.
- Añadir un menú lateral de navegación presente en las tres páginas, con la sección activa resaltada y acceso al estado de administración, login y logout.
- Mantener el refresco automático en Inicio y Tareas, y desactivarlo en Configuración para no perder cambios mientras se edita un formulario.
- Redirigir los mensajes de éxito y error de cada acción a la página correspondiente.
- Reutilizar el contrato de token de TMDB definido en `pais-origen-tmdb`; este cambio solo reubica su configuración en Configuración. Se recomienda aplicar `pais-origen-tmdb` antes o junto con este cambio.
- No se añaden tablas, migraciones ni dependencias nuevas.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `dashboard-ingesta`: se separan estados, tareas y configuración en páginas navegables, se añade el menú lateral, se reubican las acciones y formularios y se ajusta el refresco automático por página.

## Impact

- `src/mediateca/dashboard/app.py`: rutas `GET /tareas` y `GET /configuracion`, contexto por página y redirecciones de los POST a la página correspondiente.
- `src/mediateca/dashboard/templates/`: plantilla base con menú lateral y plantillas de Inicio, Tareas, Configuración y estado degradado.
- `src/mediateca/dashboard/queries.py`: se reutilizan las consultas existentes; solo se ajusta lo necesario para el contexto de cada página.
- `src/mediateca/dashboard/templates/dashboard.html`: se sustituye por la plantilla de Inicio y la base compartida.
- `tests/test_dashboard.py`: navegación, separación de contenido, redirecciones y protección de escritura en las nuevas páginas.
- `README.md`: descripción de las páginas, del menú y de dónde se configura cada integración.
- Sin cambios en PostgreSQL, Meilisearch, `docker-compose.yml` ni en la API de observabilidad.
- Dependencia de planificación: `pais-origen-tmdb`, que define el token de TMDB y su sección de dashboard.
