BEGIN;
SET LOCAL lock_timeout = '5s';
SELECT pg_advisory_xact_lock(731593001);

ALTER TABLE dishes ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1 CHECK (version > 0);

INSERT INTO reservation_schema_versions(version) VALUES (4) ON CONFLICT (version) DO NOTHING;
COMMIT;
