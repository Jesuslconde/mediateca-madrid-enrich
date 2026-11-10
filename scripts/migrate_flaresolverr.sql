-- Configuracion persistida de la ingesta.
-- Idempotente: puede ejecutarse varias veces sin error.

CREATE TABLE IF NOT EXISTS app_config (
    key VARCHAR(64) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
