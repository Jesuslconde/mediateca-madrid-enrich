-- Elimina el estado de prestamo y el historial de disponibilidad de esquemas anteriores.
-- Es idempotente: puede ejecutarse varias veces sin error.

DROP TABLE IF EXISTS historial_disponibilidad;

ALTER TABLE IF EXISTS ediciones DROP COLUMN IF EXISTS disponible;
ALTER TABLE IF EXISTS ejemplares DROP COLUMN IF EXISTS disponible;
ALTER TABLE IF EXISTS ejemplares DROP COLUMN IF EXISTS estado;
