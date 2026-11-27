BEGIN;
SET LOCAL lock_timeout = '5s';
SELECT pg_advisory_xact_lock(731593001);

CREATE TABLE IF NOT EXISTS customer_recovery (
    customer_phone TEXT PRIMARY KEY REFERENCES customers(customer_phone),
    email TEXT NOT NULL, verified_at BIGINT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS account_tokens (
    token_hash TEXT PRIMARY KEY,
    customer_phone TEXT NOT NULL REFERENCES customers(customer_phone),
    purpose TEXT NOT NULL CHECK(purpose IN ('verify_email','reset_password')),
    email TEXT NOT NULL, password_fingerprint TEXT NOT NULL,
    created_at BIGINT NOT NULL, expires_at BIGINT NOT NULL, consumed_at BIGINT
);
CREATE INDEX IF NOT EXISTS idx_account_tokens_owner ON account_tokens(customer_phone,purpose);
CREATE TABLE IF NOT EXISTS account_mail_limits (
    limit_key TEXT PRIMARY KEY, last_attempt_at BIGINT NOT NULL,
    window_started_at BIGINT NOT NULL, attempts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS account_link_requests (
    link_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    target_type TEXT NOT NULL CHECK(target_type IN ('booking','visit','queue')),
    target_id INTEGER NOT NULL,
    candidate_phone TEXT NOT NULL REFERENCES customers(customer_phone),
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','confirmed','declined','expired')),
    created_at BIGINT NOT NULL, expires_at BIGINT NOT NULL, resolved_at BIGINT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_account_link_pending
    ON account_link_requests(target_type,target_id,candidate_phone) WHERE status='pending';

INSERT INTO reservation_schema_versions(version) VALUES (8) ON CONFLICT (version) DO NOTHING;
COMMIT;
