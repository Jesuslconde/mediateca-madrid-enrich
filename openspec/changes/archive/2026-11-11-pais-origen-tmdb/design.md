# Design

## Context

Ver `proposal.md` para la motivación y las delta specs para el contrato de comportamiento. El enriquecimiento actual descarga la ficha del OPAC, la parsea y actualiza la edición y sus ejemplares en PostgreSQL. El modelo `Edicion` y los esquemas de la API viven en el wheel compartido `mediateca-shared`, que consumen tanto este repositorio como `mediateca-madrid`. El índice de Meilisearch se construye en `src/mediateca/catalog/indexer.py`, pero la API y el portal leen el mismo índice desde el repositorio hermano.

El campo `Edicion.pais` existe y se rellena con el código de país de la posición 15-17 del MARC 008. Es un dato único, a menudo vacío o incompleto, y no se puede sustituir sin perder trazabilidad del OPAC.

## Goals / Non-Goals

**Goals:**

- Obtener países de origen normalizados de TMDB sin sustituir el `pais` del OPAC.
- Integrar TMDB en el enriquecimiento de fichas nuevas y ofrecer un backfill manual reanudable.
- Mantener la ingesta del OPAC operativa si TMDB no está configurado, falla o limita las peticiones.
- Exponer `paises_origen` como campo filtrable y faceta en Meilisearch para que el cambio frontal pueda consumirlo.
- Versionar el esquema compartido de forma que ambos repositorios detecten la incompatibilidad antes de leer los nuevos campos.

**Non-Goals:**

- Implementar el filtro visible, la API o los textos del portal; eso se planifica en `mediateca-madrid`.
- Sustituir o eliminar el `pais` del OPAC.
- Traducir títulos ni corregir metadatos del OPAC con TMDB más allá de los países de origen.
- Resolver automáticamente desambiguaciones ambiguas por director, reparto o EAN.
- Enriquecer con TMDB las ediciones stub que aún no tienen título y año fiables.

## Decisions

### 1. Cliente TMDB aislado sobre `httpx`

Nuevo módulo `src/mediateca/catalog/tmdb.py` con un cliente que usa `httpx` y la API de TMDB. Expone dos operaciones: búsqueda de película (`/3/search/movie`) y detalle (`/3/movie/{id}`). No se añaden librerías nuevas. El cliente SHALL aceptar dos credenciales: una API Key v3, enviada como parámetro `api_key` en la consulta, y un Read Access Token v4, enviado como `Authorization: Bearer <token>`. El formato se detecta por la forma del token: los JWT (empiezan por `eyJ` y contienen dos caracteres `.`) usan Bearer; el resto se trata como API Key v3.

- **Por qué**: TMDB ofrece ambas credenciales y el operador puede tener solo una; aceptar las dos evita fricción.
- **Alternativa descartada**: exigir solo Bearer; muchos operadores tienen una API Key v3.
- **Alternativa descartada**: exigir solo `api_key`; expone el secreto en la URL y en logs de proxy, por lo que se prefiere Bearer cuando el token lo permite.
- **Riesgo mitigado**: con API Key v3 el secreto viaja en la query; se usa HTTPS, no se registran URLs completas y el dashboard no muestra el token.
- **Alternativa descartada**: una librería cliente de TMDB; no aporta nada frente a dos endpoints y añade dependencia.

### 2. Configuración opcional y aislada

`Settings` gana `tmdb_api_token`, `tmdb_language` (`es-ES` por defecto), `tmdb_delay` (0,25 s por defecto), `tmdb_timeout` (10 s) y `tmdb_max_retries` (3). Se propagan a `worker`, que es quien ejecuta el enriquecimiento y el backfill. El token efectivo se resuelve al iniciar cada trabajo: primero `app_config` (`tmdb_api_token`, configurado desde el dashboard), después `MEDIATECA_TMDB_API_TOKEN` y, si no hay ninguno, se omite el enriquecimiento TMDB. El resto de ajustes siguen viniendo de `Settings`.

- **Por qué**: TMDB es una fuente externa opcional; el sistema debe funcionar igual que hoy sin configurarla, y el operador debe poder activarla desde el dashboard.
- **Alternativa descartada**: activar TMDB por defecto con una clave de ejemplo; produciría errores 401 y ruido en los lotes.
- **Nota**: el detalle de la configuración persistida está en la decisión 10.

### 3. Emparejamiento conservador por título y año

Para cada edición se construyen candidatos de título a partir de `titulo_uniforme` y `titulo`: se colapsan espacios, se recorta la puntuación final (`/`, `:`, `;`, `,`, `.`) y se prueba el título completo y el segmento anterior a ` / ` cuando exista. Se consulta `/search/movie` con `language`, `year` y `include_adult=false`. Se acepta un resultado solo si:

- el año de `release_date` está a menos de un año del año de la edición, y
- el título normalizado coincide exactamente con `title` u `original_title`, o la similitud (`difflib.SequenceMatcher`) es al menos 0,90.

Si hay varios candidatos válidos se elige el de mayor similitud y, en empate, el de mayor `popularity`. Si la edición no tiene año, solo se acepta una coincidencia exacta de título normalizado. Si no hay coincidencia fiable, no se escribe ningún campo TMDB y la edición queda pendiente.

- **Por qué**: TMDB busca por texto y puede devolver remakes, secuelas o títulos homónimos; exigir año y similitud reduce falsos positivos.
- **Alternativa descartada**: aceptar el primer resultado de búsqueda; produciría países incorrectos en títulos genéricos.
- **Alternativa descartada**: usar EAN o director como clave principal; TMDB no indexa EAN y el director exigiría una llamada extra de créditos sin garantía de coincidencia.

### 4. Países de producción con respaldo de país de origen

Tras una coincidencia fiable se consulta `/3/movie/{id}` y se usan `production_countries[].iso_3166_1` como fuente principal. Si viene vacío, se usa `origin_country` como lista de un elemento. Los códigos se normalizan a mayúsculas, se deduplican conservando el orden y se guardan como `paises_origen`. Una película emparejada sin países guarda una lista vacía y sí se marca como sincronizada.

- **Por qué**: `production_countries` refleja coproducciones y es la lista más completa; `origin_country` cubre los casos en que TMDB no informa producción.
- **Alternativa descartada**: guardar nombres de país en español; ata el dato al idioma y complica filtros estables. El portal traducirá los códigos ISO con sus etiquetas.

### 5. Integración best-effort en el enriquecimiento del OPAC

`Harvester._enrich_titn` guarda primero la ficha del OPAC como hoy y, después, intenta el enriquecimiento TMDB de la edición guardada. Un fallo de TMDB se registra y no relanza la excepción: la ficha del OPAC queda enriquecida y `tmdb_enriched_at` permanece vacío. `CaptchaRequired` del OPAC sigue propagándose sin cambios. El token efectivo se resuelve al inicio del trabajo y se pasa al cliente; un cambio guardado en el dashboard se aplica al siguiente trabajo, no al que ya está en ejecución.

Las estadísticas del lote añaden contadores `tmdb_matched`, `tmdb_unmatched`, `tmdb_errors` y `tmdb_skipped`, visibles en `harvest_jobs.stats` y en los logs del lote. No se amplían el dashboard ni los esquemas de observabilidad salvo que el operador los consulte en las estadísticas del trabajo. El índice se actualiza con los TITN procesados como hasta ahora, de modo que `paises_origen` llega a Meilisearch al terminar el lote.

- **Por qué**: TMDB es un complemento; una caída de TMDB no debe impedir completar la cobertura del OPAC.
- **Alternativa descartada**: abortar la ficha si TMDB falla; convertiría una dependencia opcional en un bloqueo de la ingesta.
- **Alternativa descartada**: dejar TMDB solo en el backfill; las fichas nuevas no tendrían país durante días.

### 6. Backfill manual por comando de CLI

Nuevo comando `mediateca tmdb-enrich --limit N --delay S`. Selecciona ediciones con `detail_fetched_at` no vacío y `tmdb_enriched_at` vacío, ordenadas por `titn`, y procesa hasta el límite. Tras cada edición confirmada actualiza la edición y, al terminar, indexa los TITN procesados (con opción `--no-index` para omitirlo). Informa de procesadas, emparejadas, sin coincidencia y fallidas. El comando resuelve el token efectivo (dashboard o entorno) al arrancar; si no hay token, termina con un error legible sin modificar ediciones.

- **Por qué**: el backfill es una operación manual sobre decenas de miles de fichas; un comando por lotes permite reanudar y controlar el coste de TMDB.
- **Alternativa descartada**: un nuevo tipo de trabajo en `harvest_jobs`; amplía el worker, el dashboard y las constantes compartidas sin que el usuario lo haya pedido.
- **Nota**: las ediciones sin coincidencia no se marcan como sincronizadas y se reintentan en ejecuciones posteriores. El operador controla el tamaño del lote y puede repetir solo cuando el catálogo o la estrategia de emparejamiento mejoren.

### 7. Modelo compartido y migración

En `mediateca-madrid-shared` se añaden a `Edicion` las columnas `paises_origen` (JSON, por defecto `[]`), `tmdb_id` (entero opcional) y `tmdb_enriched_at` (timestamp opcional), y se añade `paises_origen` a `SearchHit` y `RecordDetail`. Se sube `SCHEMA_VERSION` a `2` y la versión del paquete a `0.2.0`, se reconstruye el wheel y se actualizan los `vendor/` de este repositorio y de `mediateca-madrid`.

En este repositorio se añade `scripts/migrate_tmdb.sql`, idempotente, con `ALTER TABLE ediciones ADD COLUMN IF NOT EXISTS` y la actualización de `schema_meta.schema_version` a `2`. `make migrate` lo ejecuta después de las migraciones existentes. `init_db` crea las columnas en instalaciones nuevas a través de los modelos compartidos.

- **Por qué**: la API y la ingesta comparten el modelo; un cambio de columnas sin versión de esquema dejaría a `mediateca-madrid` leyendo columnas inexistentes o ignorando las nuevas.
- **Alternativa descartada**: guardar los países en `notas` o `marc`; impide filtrar en Meilisearch y mezcla datos derivados con metadatos del OPAC.
- **Alternativa descartada**: duplicar el modelo en cada repositorio; rompe la fuente única compartida.

### 8. Índice y contrato de búsqueda

`build_document` añade `paises_origen` (lista, vacía si no hay). `FILTERABLE_ATTRIBUTES` y `FACET_FIELDS` incorporan `paises_origen`; `build_filters` acepta un filtro por uno o varios países y lo combina con los existentes. La API del repositorio hermano replicará el mismo campo y filtro en su capa de búsqueda.

- **Por qué**: Meilisearch exige declarar el atributo como filtrable y como faceta para devolver su distribución.
- **Alternativa descartada**: filtrar en PostgreSQL; rompe el patrón de búsqueda actual y no escala con el índice.

### 9. Atribución y condiciones de uso de TMDB

La documentación de este repositorio y el cambio frontal deben indicar que el producto usa la API de TMDB y mostrar la atribución exigida por sus términos. No se cachean imágenes ni datos más allá de los campos normalizados del catálogo.

- **Por qué**: TMDB exige atribución y limita el uso de su API; el dato derivado se guarda, pero la marca debe ser visible en el portal.
- **Alternativa descartada**: omitir la atribución; incumple las condiciones de uso.

### 10. Configuración del token de TMDB desde el dashboard

El dashboard añade la sección "Configuración de TMDB" y la ruta `POST /config/tmdb`, protegida por el token de administración. El token se guarda en `app_config` con la clave `tmdb_api_token`; se valida (sin espacios ni caracteres de control, con una longitud acotada) y se normaliza. La vista muestra el origen (`dashboard`, `entorno` o `ninguno`), el estado activo y solo una máscara del token. El campo se envía vacío por defecto para no reexponer el secreto; un envío vacío conserva el token y una casilla explícita permite borrarlo. Un error de validación o de base de datos no cambia la configuración vigente. El token nunca se registra en logs ni se incluye en mensajes de error.

- **Por qué**: el operador puede activar TMDB sin editar `.env` ni reconstruir contenedores, y el secreto no queda visible en la interfaz.
- **Alternativa descartada**: editar solo la variable de entorno; exige reiniciar el worker y no es práctico desde el dashboard.
- **Alternativa descartada**: precargar el token completo en el campo; lo expone en el HTML y en el historial del navegador.
- **Alternativa descartada**: borrar con el campo vacío, como FlareSolverr; en un secreto es fácil de provocar por accidente, así que se exige una casilla.
- **Riesgo aceptado**: `app_config` guarda el token en texto plano, igual que la URL de FlareSolverr. Se mitiga con acceso restringido al dashboard, HTTPS y no exponerlo públicamente; el cifrado en reposo queda fuera de alcance.

## Risks / Trade-offs

- [Falsos positivos de TMDB] Títulos genéricos o remakes pueden emparejar con la película equivocada. → Se exige año dentro de ±1 y similitud ≥ 0,90; las coincidencias dudosas quedan sin países y se registran.
- [Coste y límites de TMDB] Dos llamadas por edición y decenas de miles de fichas pueden agotar la cuota o tardar horas. → Retardo configurable, reintentos con backoff, backfill por lotes y respeto del `Retry-After`.
- [Caída de TMDB] El enriquecimiento no debe bloquearse. → TMDB es best-effort; el fallo se registra y la ficha del OPAC se conserva.
- [Reintentos infinitos de no coincidentes] El backfill vuelve a probar ediciones sin `tmdb_enriched_at`. → El operador controla el lote y puede repetir cuando mejore el catálogo; se documenta el comportamiento.
- [Cambio de esquema compartido] La versión `2` invalida a los consumidores con el wheel `0.1.0`. → Se actualizan ambos `vendor/` y `SCHEMA_VERSION`; la API falla al arrancar con un error legible hasta actualizar.
- [Faceta incompleta] Los documentos antiguos no tendrán `paises_origen` hasta reindexar. → Se requiere `mediateca index --reset` tras la migración y el backfill; los TITN nuevos se indexan de forma incremental.
- [Atribución de TMDB] El portal podría no mostrar la atribución exigida. → Se incluye como requisito del cambio frontal y se documenta en este repositorio.
- [Idioma de búsqueda] `es-ES` puede no encontrar títulos cuyo título en español difiere del original. → Se prueban `titulo_uniforme` y `titulo` como candidatos y se acepta `original_title` en la comparación.
- [Secreto en texto plano] `app_config` guarda el token sin cifrar. → Se muestra enmascarado, no se registra en logs, el dashboard no debe exponerse públicamente y las escrituras exigen el token de administración; el cifrado en reposo queda fuera de alcance.
- [API Key v3 en la URL] La autenticación v3 envía el token como parámetro de consulta. → Se usa HTTPS, no se registran URLs completas y se prefiere Bearer cuando el token es v4.
- [Cambio en caliente] Un trabajo largo no adopta un token guardado a mitad de ejecución. → El token se resuelve al inicio de cada trabajo; el dashboard indica que la configuración aplica a los siguientes trabajos.
- [Token guardado inválido] Una fila antigua o corrupta en `app_config` podría romper la consulta. → Se valida al leer; si es inválida se ignora y se usa el entorno, o se omite TMDB.
- [Máscara insuficiente] Mostrar sufijos del token puede ayudar a identificarlo, pero no debe revelar suficiente para usarlo. → Se muestran como máximo los últimos cuatro caracteres y nunca el valor completo.

## Migration Plan

1. Actualizar `mediateca-madrid-shared`: columnas, esquemas, `SCHEMA_VERSION` y versión del paquete; reconstruir el wheel y ejecutar sus tests.
2. Sustituir el wheel en `vendor/` de `mediateca-madrid-enrich` y actualizar la dependencia de `pyproject.toml`; repetir en `mediateca-madrid`.
3. Añadir `scripts/migrate_tmdb.sql` y su línea en `make migrate`; ejecutarlo dos veces sobre PostgreSQL. La tabla `app_config` ya existe, así que no hace falta una migración nueva para el token.
4. Implementar el cliente TMDB (API Key v3 y Read Access Token v4) y su configuración; añadir tests con transporte simulado.
5. Añadir la configuración del token al dashboard: `config_store`, consulta, ruta `POST /config/tmdb`, plantilla y tests de precedencia, máscara, borrado y no exposición en logs.
6. Integrar el enriquecimiento best-effort y los contadores en el lote del OPAC, resolviendo el token efectivo al inicio del trabajo.
7. Añadir el comando de backfill y la indexación de los TITN procesados, usando el token efectivo.
8. Ampliar el índice (`paises_origen`, filtro y faceta) y reindexar con `mediateca index --reset`.
9. Actualizar `README.md` y `docs/ARCHITECTURE.md`; ejecutar `pytest -q` y `ruff check src tests`.
10. Planificar y aplicar el cambio frontal en `mediateca-madrid` (filtro de API y portal) después de que el índice exponga la faceta.

**Rollback**: borrar el token desde el dashboard o su fila de `app_config` desactiva el enriquecimiento y el backfill si no hay variable de entorno; vaciar solo `MEDIATECA_TMDB_API_TOKEN` no desactiva TMDB mientras exista un token guardado. Las columnas nuevas son inofensivas para el código anterior; si se revierte el wheel, hay que volver a la versión `1` del esquema y desplegar ambos repositorios de forma coordinada. Los documentos de Meilisearch conservan `paises_origen` hasta la siguiente reindexación, pero el código antiguo lo ignora.
