-- =====================================================================
--  Migration 0003 — Phase 4: auth, roles, audit + routing-stale flag
-- =====================================================================
BEGIN;

-- ---- routing-change tracking -------------------------------------------------
-- When a routing's operations change, schedules built from it are potentially
-- out of date. We flag them stale so the UI can warn and prompt a re-solve.
ALTER TABLE planned_schedule
    ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS stale_reason TEXT;

-- ---- roles & users -----------------------------------------------------------
-- Roles mirror the alert-escalation matrix from the prototype.
CREATE TYPE user_role_t AS ENUM (
    'admin', 'planner', 'supervisor', 'procurement', 'viewer'
);

CREATE TABLE app_user (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username        TEXT        NOT NULL UNIQUE,
    full_name       TEXT,
    role            user_role_t NOT NULL DEFAULT 'viewer',
    password_hash   TEXT        NOT NULL,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at   TIMESTAMPTZ
);
COMMENT ON TABLE app_user IS 'Application users with a single role; password stored as a salted hash.';

-- ---- audit log ---------------------------------------------------------------
-- Append-only record of who changed what. Written by the API on mutations.
CREATE TABLE audit_log (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_id        BIGINT      REFERENCES app_user(id) ON DELETE SET NULL,
    actor_username  TEXT,                       -- denormalised so history survives user deletion
    action          TEXT        NOT NULL,        -- e.g. 'create', 'update', 'delete', 'solve', 'login'
    entity_type     TEXT        NOT NULL,        -- e.g. 'order', 'bom_line', 'routing', 'schedule'
    entity_id       TEXT,                        -- business or numeric id as text
    detail          JSONB,                       -- optional before/after or summary
    at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_at ON audit_log(at DESC);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
COMMENT ON TABLE audit_log IS 'Append-only audit trail of user actions.';

COMMIT;
