-- Estado persistente de la ingesta masiva.
-- Idempotente: puede ejecutarse varias veces sin error.

CREATE TABLE IF NOT EXISTS schema_meta (
    key VARCHAR(64) PRIMARY KEY,
    value VARCHAR(64) NOT NULL
);

INSERT INTO schema_meta (key, value)
VALUES ('schema_version', '1')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

CREATE TABLE IF NOT EXISTS harvest_jobs (
    id SERIAL PRIMARY KEY,
    job_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    cursor_doc INTEGER,
    cursor_titn VARCHAR(32),
    batch_size INTEGER NOT NULL DEFAULT 5000,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    stats JSON NOT NULL DEFAULT '{}'::json,
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    heartbeat_at TIMESTAMP WITH TIME ZONE
);

ALTER TABLE harvest_jobs ALTER COLUMN status SET DEFAULT 'pending';
ALTER TABLE harvest_jobs ALTER COLUMN batch_size SET DEFAULT 5000;
ALTER TABLE harvest_jobs ALTER COLUMN attempts SET DEFAULT 0;
ALTER TABLE harvest_jobs ALTER COLUMN max_attempts SET DEFAULT 3;
ALTER TABLE harvest_jobs ALTER COLUMN stats SET DEFAULT '{}'::json;

CREATE INDEX IF NOT EXISTS ix_harvest_jobs_job_type ON harvest_jobs (job_type);
CREATE INDEX IF NOT EXISTS ix_harvest_jobs_status ON harvest_jobs (status);
CREATE INDEX IF NOT EXISTS ix_harvest_jobs_status_job_type
    ON harvest_jobs (status, job_type);

ALTER TABLE ediciones
    ADD COLUMN IF NOT EXISTS is_stub BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE ediciones
    ADD COLUMN IF NOT EXISTS discovery_seen_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE ediciones
    ADD COLUMN IF NOT EXISTS detail_fetched_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE ediciones
    ADD COLUMN IF NOT EXISTS missing_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE ediciones ALTER COLUMN obra_id DROP NOT NULL;

-- Las ediciones que ya existían antes de este cambio estaban enriquecidas.
-- Los stubs nuevos tienen is_stub = true y titulo = titn, así que no se tocan.
UPDATE ediciones
SET discovery_seen_at = COALESCE(discovery_seen_at, updated_at),
    detail_fetched_at = COALESCE(detail_fetched_at, updated_at)
WHERE detail_fetched_at IS NULL
  AND is_stub = false
  AND titulo <> titn
  AND source_url IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_ediciones_is_stub ON ediciones (is_stub);
CREATE INDEX IF NOT EXISTS ix_ediciones_discovery_seen_at ON ediciones (discovery_seen_at);
CREATE INDEX IF NOT EXISTS ix_ediciones_detail_fetched_at ON ediciones (detail_fetched_at);

-- Retirada de snapshots HTML: el enriquecimiento guarda solo datos parseados.
DROP TABLE IF EXISTS snapshots;
