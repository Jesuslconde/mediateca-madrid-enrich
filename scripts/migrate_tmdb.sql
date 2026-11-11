-- Enriquecimiento con TMDB: paises de origen y marcas de sincronizacion.
-- Idempotente: puede ejecutarse varias veces sin error.

CREATE TABLE IF NOT EXISTS schema_meta (
    key VARCHAR(64) PRIMARY KEY,
    value VARCHAR(64) NOT NULL
);

ALTER TABLE IF EXISTS ediciones
    ADD COLUMN IF NOT EXISTS paises_origen JSON NOT NULL DEFAULT '[]'::json;
ALTER TABLE IF EXISTS ediciones
    ADD COLUMN IF NOT EXISTS tmdb_id INTEGER;
ALTER TABLE IF EXISTS ediciones
    ADD COLUMN IF NOT EXISTS tmdb_enriched_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX IF NOT EXISTS ix_ediciones_tmdb_enriched_at
    ON ediciones (tmdb_enriched_at);

INSERT INTO schema_meta (key, value)
VALUES ('schema_version', '2')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
