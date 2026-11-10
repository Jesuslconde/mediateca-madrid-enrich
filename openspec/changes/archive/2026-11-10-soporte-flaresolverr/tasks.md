# Tasks

## 1. Configuración persistida

- [x] 1.1 Crear el modelo local `AppConfig` en `src/mediateca/core/models.py`, importarlo en `init_db` y verificar con un test que `Base.metadata.create_all` crea la tabla `app_config`
- [x] 1.2 Implementar `src/mediateca/core/config_store.py` con normalización, lectura, escritura y resolución de la URL efectiva, y verificar con tests de URL válida, inválida, con credenciales, campo vacío y precedencia base de datos sobre entorno
- [x] 1.3 Añadir `flaresolverr_url` y `flaresolverr_max_timeout_ms` a `Settings` y `.env.example`, y verificar con tests de valores por defecto y variables de entorno
- [x] 1.4 Añadir `scripts/migrate_flaresolverr.sql` idempotente y su línea en `make migrate`, y verificar ejecutándola dos veces sobre PostgreSQL local
- [x] 1.5 Documentar la tabla `app_config` y las variables de FlareSolverr en `README.md` y `docs/ARCHITECTURE.md`, y verificar que los nombres coinciden con `Settings`

## 2. Cliente FlareSolverr

- [x] 2.1 Implementar `src/mediateca/catalog/flaresolverr.py` con `FlareSolverrClient`, `FlareSolverrResponse` y `FlareSolverrError`, y verificar con tests de petición GET y POST contra un transporte simulado
- [x] 2.2 Validar en el cliente los estados de error, timeouts y respuestas incompletas de FlareSolverr, y verificar con tests que cada caso lanza un error comprensible sin exponer cookies
- [x] 2.3 Documentar el contrato `/v1`, el campo `maxTimeout` y la versión mínima asumida en `docs/ARCHITECTURE.md`, y verificar que coincide con el cliente implementado

## 3. Fallback en el recolector y métricas

- [x] 3.1 Ampliar `OpacClient` con la URL de FlareSolverr, el timeout y los contadores de captchas resueltos y fallidos, y verificar con un test de construcción y valores iniciales
- [x] 3.2 Integrar el fallback en `_request` para GET y POST, construir una respuesta compatible con `httpx`, sincronizar cookies y `User-Agent`, y verificar con tests que se reenvía la misma URL, formulario y cookies
- [x] 3.3 Implementar la política de fallo: sin URL, error de FlareSolverr o respuesta que sigue siendo captcha debe relanzar `CaptchaRequired` sin bucle, y verificar cada caso con tests
- [x] 3.4 Extender `_opac_metrics`, `IngestMetrics`, los schemas y el router de la API y la CLI con captchas resueltos y fallidos, y verificar con tests de agregación y de respuesta HTTP
- [x] 3.5 Actualizar la documentación de métricas de captcha en `docs/ARCHITECTURE.md`, y verificar que los nombres expuestos coinciden con API, CLI y base de datos

## 4. Cableado de ejecución y operación

- [x] 4.1 Resolver la URL efectiva al crear el cliente en `_discover_handler`, `_enrich_handler`, el scheduler y los comandos `harvest`, `discover` y `enrich`, y verificar con tests que el cliente recibe la URL persistida
- [x] 4.2 Propagar `MEDIATECA_FLARESOLVERR_URL` y `MEDIATECA_FLARESOLVERR_MAX_TIMEOUT_MS` en `docker-compose.yml` para worker, scheduler y dashboard, y verificar con `docker compose config` que aparecen sin añadir un servicio FlareSolverr
- [x] 4.3 Documentar en `README.md` y `docs/ARCHITECTURE.md` el comportamiento de fallback, la desactivación por defecto y los riesgos de condiciones de uso y SSRF del dashboard, y verificar que las instrucciones son ejecutables

## 5. Dashboard

- [x] 5.1 Añadir en `dashboard/queries.py` una consulta que devuelva URL guardada, URL de entorno, URL efectiva, origen y estado activo, y verificar la precedencia con tests
- [x] 5.2 Añadir la ruta `POST /config/flaresolverr` con validación, guardado, borrado y mensajes de error, y verificar con tests de URL válida, campo vacío, URL inválida y fallo de base de datos
- [x] 5.3 Actualizar `templates/dashboard.html` con el formulario de configuración, el origen, el estado activo y las métricas de captchas resueltos y fallidos, y verificar con tests que el HTML muestra los valores y mantiene el resto de secciones de solo lectura
- [x] 5.4 Documentar la sección de configuración y su alcance de escritura en `README.md`, y verificar que el texto coincide con el comportamiento del dashboard

## 6. Verificación de integración

- [x] 6.1 Ejecutar `pytest -q` en el contenedor y corregir cualquier fallo
- [x] 6.2 Ejecutar `ruff check src tests` y corregir cualquier aviso
- [x] 6.3 Verificar manualmente que sin URL de FlareSolverr un captcha detiene la recolección y que, con una URL configurada desde el dashboard, el siguiente trabajo la usa

## Workflow follow-up

- Archivar el cambio cuando la revisión del proyecto esté satisfecha.
- Verificar el resultado archivado y las specs principales actualizadas.
