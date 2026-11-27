BEGIN;
SET LOCAL lock_timeout = '5s';
SELECT pg_advisory_xact_lock(731593001);

CREATE TABLE IF NOT EXISTS web_sessions (
    token_hash TEXT PRIMARY KEY,
    staff_id INTEGER REFERENCES staff(staff_id) ON DELETE CASCADE,
    customer_phone TEXT REFERENCES customers(customer_phone) ON DELETE CASCADE,
    expires_at BIGINT NOT NULL,
    CHECK ((staff_id IS NULL) <> (customer_phone IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_web_sessions_staff ON web_sessions(staff_id);
CREATE INDEX IF NOT EXISTS idx_web_sessions_customer ON web_sessions(customer_phone);
CREATE INDEX IF NOT EXISTS idx_web_sessions_expiry ON web_sessions(expires_at);

INSERT INTO reservation_schema_versions(version) VALUES (5) ON CONFLICT (version) DO NOTHING;
COMMIT;
