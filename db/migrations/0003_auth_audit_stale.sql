-- =====================================================================
--  Migration 0005 — deployment hardening: account lockout + refresh tokens
-- =====================================================================
BEGIN;

-- Track failed logins for lockout, and lockout expiry.
ALTER TABLE app_user
    ADD COLUMN IF NOT EXISTS failed_login_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ;

-- Refresh tokens: opaque token hashes with expiry, revocable. The raw token is
-- returned to the client once; only its hash is stored.
CREATE TABLE IF NOT EXISTS refresh_token (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id      BIGINT      NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    token_hash   TEXT        NOT NULL UNIQUE,
    issued_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL,
    revoked_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_refresh_user ON refresh_token(user_id);

COMMIT;