# Design

## Context

Ver `proposal.md` para la motivación y las delta specs para el contrato de comportamiento. El cliente del OPAC vive en `src/mediateca/catalog/harvester.py` y usa `httpx` con una sesión, cookies e identificador de sesión en la URL. `_check_response` ya detecta la página de reCAPTCHA y lanza `CaptchaRequired`, que hoy aborta el trabajo.

El dashboard actual solo lee PostgreSQL y muestra trabajos, cobertura y salud del worker. La configuración del worker se resuelve por variables de entorno al construir los clientes. No hay un almacén de configuración en base de datos.

## Goals / Non-Goals

**Goals:**

- Resolver el captcha del OPAC sin cambiar el flujo normal de recolección cuando no hay captcha.
- Persistir la URL de FlareSolverr y permitir editarla desde el dashboard, con la variable de entorno como valor por defecto.
- Conservar la sesión, las cookies y el contexto de búsqueda después de una resolución.
- Exponer captchas detectados, resueltos y fallidos en las métricas existentes.
- Mantener el comportamiento actual cuando FlareSolverr no está configurado o falla.

**Non-Goals:**

- Añadir autenticación o control de acceso al dashboard.
- Gestionar el ciclo de vida del proceso FlareSolverr ni incluirlo en `docker-compose.yml`.
- Resolver captchas de otros orígenes distintos del OPAC.
- Introducir sesiones persistentes de FlareSolverr (`sessions.create`).
- Cambiar el modelo de datos del catálogo.

## Decisions

### 1. FlareSolverr solo como fallback ante captcha

El cliente mantiene `httpx` como transporte principal. Solo cuando `_check_response` detecta reCAPTCHA se invoca FlareSolverr con la misma petición. Si la resolución tiene éxito, se usa el HTML devuelto y se continúa; si falla, se comporta como hoy y el trabajo se reprograma.

- **Por qué**: la mayoría de peticiones no necesitan un navegador; el fallback reduce latencia, memoria y dependencia operativa.
- **Alternativa descartada**: enviar todo el tráfico por FlareSolverr. Añade latencia a decenas de miles de fichas y hace que todo dependa del servicio.

### 2. Cliente `FlareSolverrClient` sobre la API `/v1`

Nuevo módulo `src/mediateca/catalog/flaresolverr.py` con un cliente `httpx` que llama a `POST {url}/v1` usando `cmd=request.get` o `cmd=request.post`. Para POST se envía `postData` con el formulario codificado; para GET se codifican los parámetros en la URL. La respuesta se valida (`status == "ok"` y `solution.response`) y se devuelve un objeto con estado, HTML, URL final, cookies y user agent.

- **Por qué**: no requiere dependencias nuevas y mantiene el contrato de FlareSolverr aislado del cliente del OPAC.
- **Alternativa descartada**: usar `sessions.create` de FlareSolverr. Obliga a gestionar el ciclo de vida de una sesión de navegador y complica la reanudación y los reintentos.
- **Supuesto**: se usa la API v1 de FlareSolverr con el campo `maxTimeout` en milisegundos.

### 3. Integración en `OpacClient._request`

`OpacClient` acepta `flaresolverr_url` y `flaresolverr_max_timeout_ms`. En `_request`, al capturar `CaptchaRequired`:

1. Se incrementa el contador de captchas detectados.
2. Si no hay URL efectiva, se relanza la excepción.
3. Si hay URL, se llama a FlareSolverr con método, URL, parámetros, cuerpo y cookies actuales.
4. Se construye una respuesta `httpx.Response` con el HTML, el estado y la URL final devueltos.
5. Se incorporan las cookies devueltas a la sesión de `httpx` y se alinea el `User-Agent` con el devuelto por FlareSolverr.
6. Se valida la respuesta. Si sigue siendo captcha o la llamada falla, se cuenta como fallido, se registra y se relanza `CaptchaRequired` sin volver a llamar a FlareSolverr para esa petición.

La respuesta resuelta no vuelve a contar como captcha detectado. El reintento de sesión caducada sigue funcionando porque la respuesta sintética pasa por el mismo `_check_response`.

- **Por qué**: reutiliza el flujo de reintentos, sesión y métricas ya existente.
- **Alternativa descartada**: devolver directamente el HTML desde `_request` sin construir una respuesta. Rompe `raise_for_status`, la URL final y el manejo uniforme de errores.

### 4. Sincronización de cookies y sesión

Las cookies se envían a FlareSolverr como lista `{name, value, domain, path}` y se reincorporan con `cookies.set(...)` usando el dominio de la URL del OPAC cuando FlareSolverr no lo informa. El identificador de sesión sigue viviendo en la URL, por lo que no se modifica.

- **Por qué**: FlareSolverr resuelve el captcha en otro proceso y su navegador no comparte el cookie jar de `httpx`.
- **Riesgo mitigado**: si la sincronización no es suficiente, el flujo existente de sesión caducada renueva la sesión y vuelve a buscar.

### 5. Configuración persistida en PostgreSQL

Nueva tabla `app_config` (`key` PK, `value` texto, `updated_at`) y modelo local `AppConfig` en `src/mediateca/core/models.py`, registrado en `init_db`. El módulo `src/mediateca/core/config_store.py` expone:

- `normalize_flaresolverr_url(value)`: recorta espacios, exige `http` o `https`, rechaza credenciales embebidas, quita la barra final y limita la longitud.
- `get_config_value` / `set_config_value`: lectura y upsert; un valor vacío elimina la fila.
- `effective_flaresolverr_url(session)`: valor persistido, si existe; si no, `settings.flaresolverr_url`; si no, `None`.

La URL efectiva se resuelve al crear cada cliente del OPAC en jobs, worker, scheduler y CLI. Un cambio en el dashboard aplica al siguiente trabajo; si un captcha falla y el trabajo se reprograma, el reintento ya usa la nueva URL.

- **Por qué**: el dashboard y el worker corren en contenedores distintos; PostgreSQL es el almacén compartido que ya existe.
- **Alternativa descartada**: usar `schema_meta`; su `value` es `VARCHAR(64)` y su semántica es de versión de esquema.
- **Alternativa descartada**: un fichero compartido; exige un volumen común entre dashboard y worker y complica la coherencia.

### 6. Migración y despliegue

Añadir `scripts/migrate_flaresolverr.sql` idempotente con `CREATE TABLE IF NOT EXISTS app_config` y un índice implícito por la clave primaria. `init_db` también crea la tabla gracias a `Base.metadata.create_all`. `make migrate` ejecuta la migración después de las existentes. No se añade un servicio FlareSolverr al compose; solo se propagan `MEDIATECA_FLARESOLVERR_URL` y `MEDIATECA_FLARESOLVERR_MAX_TIMEOUT_MS` a worker, scheduler y dashboard.

### 7. Dashboard editable con alcance mínimo

El dashboard añade una sección "Configuración de FlareSolverr" con un formulario `POST /config/flaresolverr`. La ruta normaliza y valida la URL, guarda o borra el valor persistido y redirige con un mensaje. La vista muestra la URL efectiva, su origen (`dashboard`, `entorno` o `ninguno`) y si la resolución está activa. El resto de la vista sigue siendo de solo lectura; la única escritura es esa fila de configuración.

- **Por qué**: cumple la petición del operador sin convertir el dashboard en un panel de administración general.
- **Alternativa descartada**: editar la configuración por CLI. El usuario pidió explícitamente el dashboard.

### 8. Métricas

`OpacClient` mantiene `captchas`, `captchas_solved` y `captchas_failed`. `_opac_metrics` los incluye en `harvest_jobs.stats`; `IngestMetrics`, los schemas de la API, la CLI y el dashboard los agregan y muestran.

- **Por qué**: permite distinguir captchas encontrados de captchas realmente resueltos.
- **Alternativa descartada**: reutilizar solo el contador de captchas; no permite saber si FlareSolverr está funcionando.

## Risks / Trade-offs

- [Uso y condiciones del OPAC] Eludir un captcha puede contravenir las condiciones de uso del OPAC. → La función queda desactivada por defecto y el operador decide si configura FlareSolverr; se documenta el riesgo en `README.md` y `docs/ARCHITECTURE.md`.
- [SSRF desde el dashboard] Una URL editable puede apuntar a servicios internos. → Se validan solo `http`/`https`, se rechazan credenciales embebidas y se documenta que el dashboard no debe exponerse públicamente sin autenticación, que queda fuera de alcance.
- [Cambio en caliente] Un trabajo largo no adopta una URL guardada a mitad de ejecución. → El siguiente trabajo o el reintento tras un captcha fallido sí la adopta; la vista indica que la configuración aplica a nuevos trabajos.
- [Cookies incompletas] FlareSolverr puede devolver cookies sin dominio o con dominio distinto. → Se usa el host del OPAC como respaldo y el flujo de sesión caducada renueva la sesión si es necesario.
- [Latencia y memoria] FlareSolverr arranca un navegador para cada captcha. → Solo se invoca ante captcha; el timeout es configurable y un fallo no bloquea el trabajo más allá del backoff.
- [Versiones de FlareSolverr] La API v1 puede variar entre versiones. → El cliente valida `status` y `solution` y devuelve un error claro si el contrato no se cumple.
- [Contrato de solo lectura] El dashboard ahora escribe configuración. → La spec de `dashboard-ingesta` se actualiza y los tests verifican que no se escriben trabajos, ediciones ni índice.

## Migration Plan

1. Crear la tabla `app_config` con el modelo y la migración idempotente.
2. Añadir la configuración de entorno y propagarla en `docker-compose.yml` y `.env.example`.
3. Implementar `FlareSolverrClient` y sus tests con un servidor HTTP simulado.
4. Integrar el fallback y la sincronización de cookies en `OpacClient`.
5. Resolver la URL efectiva en jobs, worker, scheduler y CLI; añadir las métricas.
6. Añadir la sección y la ruta del dashboard, con validación y tests.
7. Actualizar `README.md`, `docs/ARCHITECTURE.md` y ejecutar `pytest -q` y `ruff check src tests`.

**Rollback**: borrar la URL persistida o vaciar `app_config` desactiva FlareSolverr sin tocar el código. Si se revierte el despliegue, la tabla sobrante es inofensiva y el comportamiento vuelve al actual (detener la recolección ante captcha).
