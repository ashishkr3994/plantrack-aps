-- =====================================================================
--  Migration 0004 — solver: machine eligibility + sequence-dependent setup
-- =====================================================================
BEGIN;

-- An operation may list alternate work centers it can run on (comma-separated);
-- NULL/empty means it runs only on its primary work_center.
ALTER TABLE routing_operation
    ADD COLUMN IF NOT EXISTS eligible_work_centers TEXT,
    ADD COLUMN IF NOT EXISTS setup_family TEXT;

-- Sequence-dependent changeover minutes between setup families on a machine.
CREATE TABLE IF NOT EXISTS changeover_matrix (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    from_family     TEXT        NOT NULL,
    to_family       TEXT        NOT NULL,
    changeover_min  INTEGER     NOT NULL DEFAULT 0,
    CONSTRAINT uq_changeover UNIQUE (from_family, to_family)
);

-- Record which machine the solver actually chose for each scheduled operation.
ALTER TABLE order_operation
    ADD COLUMN IF NOT EXISTS chosen_work_center TEXT;

COMMIT;