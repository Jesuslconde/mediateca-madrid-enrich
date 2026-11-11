# Tasks

## 1. Plantilla base y páginas

- [x] 1.1 Crear `templates/base.html` con el menú lateral, la sección activa, el estado de administración, login/logout, el bloque de mensajes y el refresco condicional, y crear `templates/inicio.html` con salud del worker, resumen por estado y tipo, cobertura y métricas; verificar con un test de `GET /` que aparecen los enlaces del menú, la sección `inicio` activa y ningún formulario de configuración ni tabla de trabajos
- [x] 1.2 Crear `templates/tareas.html` con la tabla de trabajos recientes y las acciones de descubrimiento, enriquecimiento e indexación; verificar con un test de `GET /tareas` que aparecen ambas secciones, la sección `tareas` activa y los botones conservan su estado deshabilitado según los trabajos activos
- [x] 1.3 Crear `templates/configuracion.html` con programación, FlareSolverr y la sección de TMDB definida en `pais-origen-tmdb`; verificar con un test de `GET /configuracion` que aparecen las tres secciones, la sección `configuracion` activa y que la página no incluye `meta http-equiv="refresh"`
- [x] 1.4 Ajustar `templates/degraded.html` para incluir un enlace a Inicio y mantener el reintento automático; verificar con un test que las tres rutas muestran el estado degradado, sin trazas, cuando la base de datos falla

## 2. Rutas, contexto y redirecciones

- [x] 2.1 Añadir las rutas `GET /tareas` y `GET /configuracion` y dividir `_dashboard_context` en contextos de estados, tareas y configuración; verificar con tests que cada página recibe solo sus datos y que `pending_titns`, `schedule` y las integraciones quedan en Configuración, y `jobs`/`active_jobs` en Tareas
- [x] 2.2 Actualizar los POST de `/jobs`, `/config/schedule`, `/config/flaresolverr` y `/config/tmdb` para redirigir a `/tareas` o `/configuracion` con `message` o `error`, y añadir un `next` validado contra `/`, `/tareas` y `/configuracion` en login, logout y errores de administración; verificar con tests de redirección correcta, `next` válido y `next` inválido
- [x] 2.3 Mantener el refresco automático solo en Inicio y Tareas y omitirlo en Configuración; verificar con tests de presencia de `meta http-equiv="refresh"` en las dos primeras y ausencia en la tercera
- [x] 2.4 Conservar la protección de escritura en las nuevas páginas; verificar con tests que sin sesión de administración las acciones de Tareas y los formularios de Configuración no escriben y que con login sí lo hacen

## 3. Contenido movido y compatibilidad

- [x] 3.1 Retirar de Inicio la tabla de trabajos recientes y las acciones bajo demanda, y comprobar con tests que ya no aparecen en `/` y sí en `/tareas`
- [x] 3.2 Retirar de Inicio la programación, FlareSolverr y TMDB, y comprobar con tests que ya no aparecen en `/` y sí en `/configuracion`
- [x] 3.3 Actualizar las pruebas del token de TMDB de `pais-origen-tmdb` para que apunten a `/configuracion`, coordinando la aplicación de ese cambio antes o junto con este; verificar que la sección conserva máscara, precedencia, borrado y no exposición en logs
- [x] 3.4 Actualizar `test_vista_es_de_solo_lectura` para recorrer `/`, `/tareas` y `/configuracion` y comprobar que ninguna carga crea, modifica ni elimina trabajos o ediciones
- [x] 3.5 Actualizar `README.md` y `docs/ARCHITECTURE.md` con las tres páginas, el menú lateral, las URLs y dónde se configura cada integración; verificar que los enlaces y comandos documentados coinciden con las rutas reales

## 4. Integración y verificación

- [x] 4.1 Ejecutar `pytest -q` y corregir cualquier fallo
- [x] 4.2 Ejecutar `ruff check src tests` y corregir cualquier aviso
- [x] 4.3 Con el dashboard levantado, recorrer el menú entre Inicio, Tareas y Configuración, encolar un trabajo, guardar cada configuración y comprobar que el mensaje aparece en la página correspondiente y que Configuración no se recarga sola
- [x] 4.4 Verificar que las URLs POST (`/jobs`, `/config/schedule`, `/config/flaresolverr`, `/config/tmdb`), el esquema de la base de datos y el `docker-compose.yml` no han cambiado
- [x] 4.5 Verificar que la sección de TMDB funciona con el cambio `pais-origen-tmdb` aplicado y anotar cualquier ajuste de coordinación en ese cambio

## Workflow follow-up

- Archivar el cambio cuando la revisión del proyecto esté satisfecha.
- Verificar el resultado archivado y las specs principales actualizadas.
- Aplicar preferentemente después de `pais-origen-tmdb`.
