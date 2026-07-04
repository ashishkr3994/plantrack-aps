-- =====================================================================
--  Migration 0002 — solve_job table for async scheduling jobs
-- =====================================================================
BEGIN;

CREATE TYPE solve_job_status_t AS ENUM ('queued', 'running', 'succeeded', 'failed');

CREATE TABLE solve_job (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id          TEXT        NOT NULL UNIQUE,          -- uuid string
    status          solve_job_status_t NOT NULL DEFAULT 'queued',
    mode            TEXT        NOT NULL DEFAULT 'forward',
    time_budget_s   INTEGER     NOT NULL DEFAULT 30,
    order_ids       JSONB,                                -- null = all orders
    result          JSONB,                                -- summary metrics when done
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ
);
CREATE INDEX idx_solve_job_status ON solve_job(status);

COMMIT;
