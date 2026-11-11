# Design

## Context

Ver `proposal.md` para la motivación y la delta spec para el contrato de comportamiento. El dashboard actual es una única plantilla `dashboard.html` servida por `GET /`; en la misma página conviven la salud del worker, la programación, las tareas bajo demanda, la configuración de FlareSolverr, la cobertura, las métricas y la tabla de trabajos recientes. Los POST de escritura (`/jobs`, `/config/schedule`, `/config/flaresolverr`, `/config/tmdb`) redirigen a `/` con el mensaje en la query.

El cambio `pais-origen-tmdb` ya planifica el token de TMDB y su sección en el dashboard. Este cambio reubica esa sección en Configuración y no redefine su validación, precedencia ni máscara.

## Goals / Non-Goals

**Goals:**

- Separar estados, tareas y configuración en tres páginas con un menú lateral común.
- Mantener intactos los contratos de datos, validación, precedencia y protección de escritura.
- Conservar los mensajes de éxito y error en la página donde se origina la acción.
- Evitar que el refresco automático borre formularios de configuración a medio editar.

**Non-Goals:**

- Añadir cancelación o reintento de trabajos existentes; esta versión solo reubica la visualización y el encolado actuales.
- Cambiar el esquema de la base de datos, la API de observabilidad o el `docker-compose.yml`.
- Añadir autenticación nueva, CSRF o un sistema de permisos distinto del token de administración existente.
- Rediseñar visualmente el dashboard más allá de la navegación y la separación de páginas.
- Cambiar el comportamiento del worker, del scheduler o de la ingesta.

## Decisions

### 1. Tres rutas y tres plantillas de página

`GET /` sirve `inicio.html`, `GET /tareas` sirve `tareas.html` y `GET /configuracion` sirve `configuracion.html`. Las rutas POST existentes conservan su URL y su lógica; solo cambia el destino de la redirección. `GET /health` no cambia.

- **Por qué**: URLs estables y separación clara de responsabilidades; los enlaces del menú son enlaces normales y funcionan sin JavaScript.
- **Alternativa descartada**: una sola página con pestañas en cliente; añade estado y JavaScript donde ahora no hay ninguno.
- **Alternativa descartada**: rutas en inglés (`/tasks`, `/settings`); la interfaz y el resto del proyecto están en español.

### 2. Plantilla base compartida con menú lateral

Nueva `base.html` con la cabecera, el menú lateral, el bloque de administración, el bloque de mensajes y un bloque `content` que rellenan las tres páginas. El menú enlaza a `/`, `/tareas` y `/configuracion`, marca la sección activa con `aria-current` y una clase, y muestra el estado de administración con login/logout. Las páginas pasan una variable `section` (`inicio`, `tareas`, `configuracion`).

- **Por qué**: evita duplicar el menú y las comprobaciones de administración en tres plantillas.
- **Alternativa descartada**: mantener una plantilla única con condicionales por ruta; vuelve a mezclar secciones y complica el mantenimiento.
- **Alternativa descartada**: un componente JavaScript de navegación; el dashboard es HTML servido por Jinja y no necesita cliente.

### 3. Contenido por página

- **Inicio**: salud del worker, resumen de trabajos por estado y tipo, cobertura del catálogo y métricas de ingesta.
- **Tareas**: tabla de trabajos recientes y acciones de descubrimiento incremental, descubrimiento completo, enriquecimiento e indexación, con el estado activo de cada tipo.
- **Configuración**: programación, URL de FlareSolverr y token de TMDB, con sus estados, formularios y mensajes.

La tabla de trabajos recientes y las acciones salen de Inicio; la programación y las integraciones también. Inicio no duplica esos bloques.

- **Por qué**: el operador consulta estados en Inicio, actúa en Tareas y ajusta parámetros en Configuración.
- **Alternativa descartada**: dejar un resumen de tareas en Inicio; mantiene la mezcla que el cambio quiere eliminar.

### 4. Refresco automático por página

La plantilla base incluye `meta http-equiv="refresh"` solo cuando la página recibe `refresh_seconds`. Inicio y Tareas reciben el valor configurado; Configuración no, para no perder los valores de un formulario a medio editar.

- **Por qué**: el refresco es útil para estados y trabajos, pero peligroso en formularios.
- **Alternativa descartada**: refrescar Configuración y preservar los valores con JavaScript; añade complejidad y no es necesario.
- **Consecuencia**: los cambios externos en Configuración se ven al recargar manualmente; se documenta.

### 5. Redirecciones y mensajes por página

Cada formulario de escritura incluye un campo oculto `next` con su página (`/tareas` o `/configuracion`). Los POST redirigen a esa página con `message` o `error`. El login y el logout aceptan un `next` limitado a `/`, `/tareas` y `/configuracion`; cualquier otro valor cae a `/`. Las redirecciones de error de administración usan el mismo `next` validado.

- **Por qué**: el operador ve el resultado donde actuó y no pierde el contexto.
- **Alternativa descartada**: redirigir siempre a `/`; obliga a volver a navegar tras cada guardado.
- **Riesgo mitigado**: un `next` arbitrario permitiría un open redirect; se valida contra una lista cerrada de rutas locales.

### 6. Carga de datos por página

`_dashboard_context` se divide en funciones de contexto por página: una para estados, otra para tareas y otra para configuración. La base recibe siempre `section`, `is_admin`, `admin_required`, `message`, `error`, `generated_at` y, cuando corresponda, `refresh_seconds`. Si la base de datos falla, cualquier página renderiza `degraded.html` con el mensaje existente, sin trazas.

- **Por qué**: cada página consulta solo lo que muestra y se mantiene el comportamiento de degradación.
- **Alternativa descartada**: cargar todo el contexto en las tres páginas; desperdicia consultas y acopla las vistas.
- **Nota**: `pending_titns` y `schedule_status` pasan al contexto de Configuración; `jobs` y `active_jobs` al de Tareas.

### 7. Compatibilidad con `pais-origen-tmdb`

La sección del token de TMDB se integra en Configuración. Se recomienda aplicar primero `pais-origen-tmdb`: si ya está aplicado, esta tarea mueve su sección desde Inicio; si no, se implementa según su spec y se coloca directamente en Configuración. Los tests del token de TMDB se actualizan para apuntar a `/configuracion`.

- **Por qué**: evita dos implementaciones divergentes del mismo formulario.
- **Alternativa descartada**: duplicar el formulario en Inicio y Configuración; rompe la separación y confunde al operador.

### 8. Estado degradado y páginas nuevas

`degraded.html` se mantiene como página independiente, con un enlace a Inicio y sin menú dependiente de datos. Las tres rutas nuevas capturan `SQLAlchemyError` y renderizan esa página con el mensaje existente.

- **Por qué**: cuando la base de datos no responde, el menú y las páginas de datos tampoco pueden funcionar con normalidad; se ofrece una salida clara.
- **Alternativa descartada**: renderizar el menú completo en estado degradado; daría la falsa impresión de que las demás secciones funcionan.

## Risks / Trade-offs

- [Enlaces antiguos] Los operadores pueden tener marcado `/` para llegar a tareas o configuración. → El menú lateral deja ambas a un clic y el README documenta las nuevas URLs.
- [Open redirect] Un `next` manipulado podría enviar al operador fuera del dashboard. → Se valida contra `/`, `/tareas` y `/configuracion`.
- [Pérdida de cambios en Configuración] Sin refresco automático, un cambio externo no se ve hasta recargar. → Se documenta y se ofrece el enlace de recarga del navegador; es preferible a borrar un formulario.
- [Duplicación de plantillas] Tres plantillas pueden divergir en el menú o los mensajes. → Todo lo común vive en `base.html` y los tests comprueban la navegación en las tres páginas.
- [Dependencia de TMDB] Si `pais-origen-tmdb` no está aplicado, la sección de token no existe todavía. → Se aplica primero ese cambio o se implementa su spec en la misma tarea de Configuración.
- [Estado degradado sin menú] El operador no puede navegar desde la página degradada. → Se muestra un enlace a Inicio y se mantiene el reintento automático.
- [Pruebas existentes] Muchas pruebas buscan contenido en `/`. → Se reparten entre `/`, `/tareas` y `/configuracion`, y se añaden comprobaciones de que Inicio no contiene lo que se movió.

## Migration Plan

1. Crear `base.html` con el menú lateral, el bloque de administración y los mensajes; adaptar `degraded.html` con un enlace a Inicio.
2. Crear `inicio.html` con los bloques de estados, cobertura y métricas; retirar de Inicio la tabla, las acciones y la configuración.
3. Crear `tareas.html` con la tabla de trabajos y las acciones actuales, conservando las reglas de encolado.
4. Crear `configuracion.html` con programación, FlareSolverr y la sección de TMDB definida en `pais-origen-tmdb`.
5. Dividir el contexto por página en `app.py` y añadir las rutas `/tareas` y `/configuracion`.
6. Ajustar las redirecciones de los POST y el login/logout con el `next` validado.
7. Actualizar los tests: navegación, separación de contenido, redirecciones, refresco y protección de escritura.
8. Actualizar `README.md` y la documentación de arquitectura del dashboard.
9. Ejecutar `pytest -q` y `ruff check src tests`.

**Rollback**: restaurar la plantilla única y la ruta `/` anterior; las rutas POST y la base de datos no cambian, así que no hay migración que deshacer. Los enlaces a `/tareas` y `/configuracion` dejan de existir, pero no afectan a la ingesta.
