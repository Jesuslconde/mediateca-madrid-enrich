# Tasks

## 1. Modelo y migración

- [x] 1.1 Añadir `HarvestJob` y los campos de progreso a `Edicion` en `backend/src/mediateca/catalog/models.py`, y verificar que `Base.metadata.tables` contiene las tablas y columnas nuevas
- [x] 1.2 Crear `scripts/migrate_ingesta.sql` con `CREATE TABLE IF NOT EXISTS` y `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, y verificar que se ejecuta dos veces sin error
- [x] 1.3 Añadir el objetivo `migrate-ingesta` al Makefile y verificar que `make help` lo muestra

## 2. Repositorio y estado

- [x] 2.1 Implementar helpers para crear, reclamar, actualizar y finalizar trabajos, y verificar con tests que un trabajo pasa de `pending` a `running` y a `completed`
- [x] 2.2 Implementar helpers de cursores y marcas de progreso por edición, y verificar que un stub pasa a enriquecido sin duplicarse
- [x] 2.3 Implementar la consulta de cobertura (descubiertas, enriquecidas, pendientes, fallidas) y verificar con datos de prueba

## 3. CLI y documentación

- [x] 3.1 Añadir `mediateca status` para mostrar trabajos y cobertura, y verificar la salida con una base de prueba
- [x] 3.2 Documentar el nuevo esquema y la migración en `docs/ARCHITECTURE.md` y `README.md`
- [x] 3.3 Ejecutar `pytest -q` y `ruff check src tests` y verificar que no hay fallos
