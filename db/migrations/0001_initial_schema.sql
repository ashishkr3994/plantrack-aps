-- =====================================================================
--  PlanTrack APS Control Tower — PostgreSQL Schema (Phase 0 deliverable)
--  Version: 1.0
--  Target:  PostgreSQL 14+
--
--  This schema is the formal, relational translation of the prototype's
--  in-browser data model. It is organised in the same dependency order
--  the engine uses:
--      Product -> BOM -> Routing -> Order -> Operation -> Schedule
--      -> Material status -> Events -> Deviations -> Alerts
--      (+ derived Capacity load and the Reschedule log)
--
--  Design notes:
--   * Surrogate BIGINT primary keys (id) on every table for stable joins,
--     plus the business/natural keys (e.g. order_id 'ORD-4312') kept as
--     UNIQUE columns so imports and the UI can reference them as today.
--   * ENUM types pin the small controlled vocabularies the engine relies on
--     (status bands, event types, scheduling mode, etc.).
--   * Every child table uses ON DELETE CASCADE / RESTRICT deliberately —
--     see each FK for the rationale.
--   * created_at / updated_at audit columns on mutable tables, maintained
--     by a shared trigger.
--   * Generated/derived tables (capacity_load) are rebuilt by the engine,
--     not hand-edited.
--
--  Run order: this file is self-contained. Execute top to bottom.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 0. EXTENSIONS & SHARED HELPERS
-- ---------------------------------------------------------------------

-- NOTE on case-sensitivity: business/natural key columns (plant_code,
-- product_id, route_id, product_family, etc.) are plain TEXT with UNIQUE
-- constraints. If you want case-insensitive uniqueness ('p-1001' == 'P-1001'),
-- enable the bundled contrib extension and switch those columns to CITEXT:
--     CREATE EXTENSION IF NOT EXISTS citext;
-- It is intentionally not required here so the schema runs on any vanilla
-- PostgreSQL without contrib packages installed.

-- Shared trigger function: keeps updated_at current on any row update.
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ---------------------------------------------------------------------
-- 1. ENUM TYPES  (controlled vocabularies the engine depends on)
-- ---------------------------------------------------------------------

-- Scheduling direction for an order / schedule version.
CREATE TYPE sched_mode_t        AS ENUM ('backward', 'forward');

-- Order priority — drives dispatch sequencing when capacity is contested.
CREATE TYPE priority_t          AS ENUM ('HIGH', 'MED', 'LOW');

-- Multi-signal order status band produced by computeOrderStatus().
CREATE TYPE order_status_t       AS ENUM ('on', 'risk', 'delay', 'crit');

-- Feasibility flag on a generated schedule (buffer >= 0 ? feasible).
CREATE TYPE schedule_status_t    AS ENUM ('feasible', 'infeasible');

-- Material procurement state per order.
CREATE TYPE material_status_t    AS ENUM ('ordered', 'ready', 'risk', 'late');

-- Shop-floor / material event types logged on the Execution screen.
CREATE TYPE event_type_t         AS ENUM (
    'material_ready', 'start', 'pause', 'resume',
    'complete', 'scrap', 'dispatch', 'delivered'
);

-- Deviation severity.
CREATE TYPE severity_t           AS ENUM ('Medium', 'High', 'Critical');

-- Deviation resolution workflow state.
CREATE TYPE resolution_status_t  AS ENUM ('Open', 'In progress', 'Resolved');

-- Alert lifecycle.
CREATE TYPE alert_status_t       AS ENUM ('open', 'ack', 'closed');

-- Alert visual/severity class (matches the UI's crit/warn/info icons).
CREATE TYPE alert_type_t         AS ENUM ('crit', 'warn', 'info');


-- ---------------------------------------------------------------------
-- 2. REFERENCE / MASTER DATA
--    (editable in the Configuration screen; rarely changes at runtime)
-- ---------------------------------------------------------------------

-- 2.1 PLANT --------------------------------------------------------------
-- Multi-plant support. Orders and shifts belong to a plant.
CREATE TABLE plant (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plant_code      TEXT        NOT NULL UNIQUE,          -- e.g. 'Plant A'
    plant_name      TEXT        NOT NULL,
    location        TEXT,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE plant IS 'Manufacturing plants/sites. Supports multi-plant scheduling.';

-- 2.2 PLANT CALENDAR (shift definitions) --------------------------------
-- Configuration -> Plant calendar. Drives WORKING_MINS_PER_DAY and
-- the working-day / holiday logic in the scheduling engine.
CREATE TABLE plant_calendar (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plant_id        BIGINT      NOT NULL REFERENCES plant(id) ON DELETE CASCADE,
    shift_name      TEXT        NOT NULL,                 -- 'Shift A'
    start_time      TIME        NOT NULL,                 -- '06:00'
    end_time        TIME        NOT NULL,                 -- '14:00'
    available_min   INTEGER     NOT NULL CHECK (available_min BETWEEN 0 AND 1440),
    days_active     TEXT        NOT NULL DEFAULT 'Mon-Sat',-- human-readable pattern
    is_holiday      BOOLEAN     NOT NULL DEFAULT FALSE,    -- holiday flag
    holiday_date    DATE,                                  -- specific holiday day, if any
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_calendar_shift UNIQUE (plant_id, shift_name, holiday_date)
);
COMMENT ON TABLE plant_calendar IS 'Shift availability and holidays per plant; sums to working minutes/day.';

-- 2.3 LEAD TIME MASTER --------------------------------------------------
-- Configuration -> Lead time master. Keyed by product family.
-- Feeds the LEAD_TIMES lookup used in schedule generation.
CREATE TABLE lead_time_master (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_family  TEXT        NOT NULL UNIQUE,           -- 'Mechanical'
    inbound_days    NUMERIC(6,2) NOT NULL DEFAULT 0 CHECK (inbound_days   >= 0),
    qa_days         NUMERIC(6,2) NOT NULL DEFAULT 0 CHECK (qa_days        >= 0),
    packing_days    NUMERIC(6,2) NOT NULL DEFAULT 0 CHECK (packing_days   >= 0),
    transport_days  NUMERIC(6,2) NOT NULL DEFAULT 0 CHECK (transport_days >= 0),
    buffer_days     NUMERIC(6,2) NOT NULL DEFAULT 0 CHECK (buffer_days    >= 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE lead_time_master IS 'Per-family inbound/QA/packing/transport/buffer lead times (days).';

-- 2.4 ALERT THRESHOLDS --------------------------------------------------
-- Configuration -> Alert thresholds. A flat key/value store the engine
-- reads to classify risk (e.g. risk_slip_hrs, buffer_crit_pct,
-- mat_risk_window_days, mat_staging_days).
CREATE TABLE alert_threshold (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    threshold_key   TEXT        NOT NULL UNIQUE,           -- 'risk_slip_hrs'
    label           TEXT        NOT NULL,
    value           NUMERIC(10,2) NOT NULL,
    unit            TEXT        NOT NULL,                  -- 'hrs','%','days','min'
    fires_when      TEXT,                                  -- human description
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE alert_threshold IS 'Editable engine thresholds; read at every recalculation.';


-- ---------------------------------------------------------------------
-- 3. PRODUCT, BOM & ROUTING
--    (the manufacturing definition: what we make and how)
-- ---------------------------------------------------------------------

-- 3.1 ROUTING (header) --------------------------------------------------
-- A route is a named process flow (e.g. 'R-STD-01'). Products point at one.
CREATE TABLE routing (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    route_id        TEXT        NOT NULL UNIQUE,           -- 'R-STD-01'
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE routing IS 'Named process flow; the ordered set of operations lives in routing_operation.';

-- 3.2 ROUTING OPERATION (template steps) --------------------------------
-- Configuration -> Routing & operations. The reusable operation template
-- for a route. Per-order copies are materialised into order_operation.
-- predecessor_seq + parallel_group encode sequence and concurrency.
CREATE TABLE routing_operation (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    routing_id          BIGINT  NOT NULL REFERENCES routing(id) ON DELETE CASCADE,
    operation_seq       INTEGER NOT NULL,                  -- 10, 20, 30 ...
    work_center         TEXT    NOT NULL,                  -- 'Machining'
    setup_min           NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (setup_min        >= 0),
    run_per_unit_min    NUMERIC(10,4) NOT NULL DEFAULT 0 CHECK (run_per_unit_min >= 0),
    queue_min           NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (queue_min        >= 0),
    move_min            NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (move_min         >= 0),
    predecessor_seq     INTEGER,                           -- NULL = first op
    parallel_group      TEXT,                              -- same group = concurrent
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_routing_op UNIQUE (routing_id, operation_seq)
);
COMMENT ON TABLE routing_operation IS 'Operation template per route: times, predecessor link, parallel group.';
CREATE INDEX idx_routing_op_routing ON routing_operation(routing_id);

-- 3.3 PRODUCT -----------------------------------------------------------
CREATE TABLE product (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id      TEXT        NOT NULL UNIQUE,           -- 'P-1001'
    name            TEXT        NOT NULL,                  -- 'Gear Housing A2'
    family          TEXT        NOT NULL,                  -- FK-by-value to lead_time_master.product_family
    routing_id      BIGINT      REFERENCES routing(id) ON DELETE SET NULL,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE product IS 'Finished products; family drives lead times, routing drives operations.';
COMMENT ON COLUMN product.family IS 'Matches lead_time_master.product_family (kept as value, families are reference data).';
CREATE INDEX idx_product_routing ON product(routing_id);
CREATE INDEX idx_product_family  ON product(family);

-- 3.4 BOM (Bill of Materials) -------------------------------------------
-- Materials & BOM -> BOM by product. Raw-material lines per product.
-- The longest lead_days across a product's lines drives material readiness.
CREATE TABLE bom_line (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id      BIGINT      NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    material        TEXT        NOT NULL,                  -- 'Cast iron blank'
    qty_per_unit    NUMERIC(12,4) NOT NULL CHECK (qty_per_unit > 0),
    uom             TEXT        NOT NULL,                  -- 'kg','pcs','set'
    supplier        TEXT,
    lead_days       INTEGER     NOT NULL DEFAULT 0 CHECK (lead_days >= 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE bom_line IS 'Raw materials required per finished product, with supplier lead time.';
CREATE INDEX idx_bom_product ON bom_line(product_id);


-- ---------------------------------------------------------------------
-- 4. TRANSACTIONAL CORE
--    (the live plan: orders, their operations, and schedule versions)
-- ---------------------------------------------------------------------

-- 4.1 ORDER HEADER ------------------------------------------------------
CREATE TABLE order_header (
    id                       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id                 TEXT        NOT NULL UNIQUE,  -- 'ORD-4312'
    product_id               BIGINT      NOT NULL REFERENCES product(id) ON DELETE RESTRICT,
    customer                 TEXT        NOT NULL,
    order_qty                INTEGER     NOT NULL CHECK (order_qty > 0),
    order_date               DATE        NOT NULL,         -- release date
    committed_delivery_date  DATE        NOT NULL,         -- customer promise
    priority                 priority_t  NOT NULL DEFAULT 'MED',
    plant_id                 BIGINT      REFERENCES plant(id) ON DELETE SET NULL,
    sched_mode               sched_mode_t NOT NULL DEFAULT 'backward',
    replan_count             INTEGER     NOT NULL DEFAULT 0 CHECK (replan_count >= 0),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (committed_delivery_date >= order_date)
);
COMMENT ON TABLE order_header IS 'Customer/production orders. RESTRICT on product so a referenced product cannot be deleted.';
CREATE INDEX idx_order_product  ON order_header(product_id);
CREATE INDEX idx_order_plant    ON order_header(plant_id);
CREATE INDEX idx_order_delivery ON order_header(committed_delivery_date);

-- 4.2 PLANNED SCHEDULE (versioned) --------------------------------------
-- One row per order per version. Version 1 = baseline; reschedules add
-- higher versions while the baseline is preserved for comparison.
CREATE TABLE planned_schedule (
    id                        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    schedule_id               TEXT        NOT NULL UNIQUE, -- 'SCH-ORD-4312-v1'
    order_id                  BIGINT      NOT NULL REFERENCES order_header(id) ON DELETE CASCADE,
    baseline_version          INTEGER     NOT NULL CHECK (baseline_version >= 1),
    sched_mode                sched_mode_t NOT NULL,
    planned_material_ready_dt TIMESTAMPTZ NOT NULL,
    planned_prod_start_dt     TIMESTAMPTZ NOT NULL,
    planned_prod_end_dt       TIMESTAMPTZ NOT NULL,
    planned_pack_dt           TIMESTAMPTZ NOT NULL,
    planned_dispatch_dt       TIMESTAMPTZ NOT NULL,
    planned_delivery_dt       TIMESTAMPTZ NOT NULL,
    prod_duration_mins        NUMERIC(12,2) NOT NULL CHECK (prod_duration_mins >= 0),
    original_buffer_hrs       NUMERIC(10,2) NOT NULL,
    buffer_hrs                NUMERIC(10,2) NOT NULL,
    schedule_status           schedule_status_t NOT NULL,
    is_current                BOOLEAN     NOT NULL DEFAULT TRUE, -- latest version flag
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_schedule_version UNIQUE (order_id, baseline_version),
    CHECK (planned_prod_start_dt <= planned_prod_end_dt),
    CHECK (planned_prod_end_dt   <= planned_delivery_dt)
);
COMMENT ON TABLE planned_schedule IS 'Versioned milestone schedule. is_current marks the latest version for an order.';
CREATE INDEX idx_schedule_order   ON planned_schedule(order_id);
-- Only one current version per order:
CREATE UNIQUE INDEX uq_schedule_current ON planned_schedule(order_id) WHERE is_current;

-- 4.3 ORDER OPERATION (scheduled, per order per version) ----------------
-- Materialised copy of the routing steps for a specific order/version,
-- with concrete planned start/end. Cascades when the order is deleted.
CREATE TABLE order_operation (
    id                          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_operation_id          TEXT        NOT NULL,      -- 'ORD-4312-OP10'
    order_id                    BIGINT      NOT NULL REFERENCES order_header(id) ON DELETE CASCADE,
    schedule_id                 BIGINT      REFERENCES planned_schedule(id) ON DELETE CASCADE,
    operation_seq               INTEGER     NOT NULL,
    work_center                 TEXT        NOT NULL,
    setup_time_min              NUMERIC(10,2) NOT NULL DEFAULT 0,
    run_time_per_unit_min       NUMERIC(10,4) NOT NULL DEFAULT 0,
    queue_time_min              NUMERIC(10,2) NOT NULL DEFAULT 0,
    move_time_min               NUMERIC(10,2) NOT NULL DEFAULT 0,
    planned_qty                 INTEGER     NOT NULL CHECK (planned_qty >= 0),
    predecessor_operation_seq   INTEGER,
    parallel_group              TEXT,
    planned_start               TIMESTAMPTZ NOT NULL,
    planned_end                 TIMESTAMPTZ NOT NULL,
    duration_mins               NUMERIC(12,2) NOT NULL CHECK (duration_mins >= 0),
    version                     INTEGER     NOT NULL DEFAULT 1,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_order_op UNIQUE (order_id, version, operation_seq),
    CHECK (planned_start <= planned_end)
);
COMMENT ON TABLE order_operation IS 'Per-order scheduled operations with planned windows; the unit of capacity loading.';
CREATE INDEX idx_op_order        ON order_operation(order_id);
CREATE INDEX idx_op_schedule     ON order_operation(schedule_id);
CREATE INDEX idx_op_wc_start     ON order_operation(work_center, planned_start);


-- ---------------------------------------------------------------------
-- 5. STATUS, EVENTS & EXCEPTIONS
--    (execution reality and what the engine derives from it)
-- ---------------------------------------------------------------------

-- 5.1 MATERIAL STATUS (one row per order) -------------------------------
-- Materials & BOM -> Procurement status. Derived from the order's BOM;
-- flips to 'late' on a late material_ready event, or 'risk' proactively
-- when the planned ready date is approaching unconfirmed.
CREATE TABLE material_status (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id          BIGINT      NOT NULL UNIQUE REFERENCES order_header(id) ON DELETE CASCADE,
    product_id        BIGINT      NOT NULL REFERENCES product(id) ON DELETE RESTRICT,
    material_count    INTEGER     NOT NULL DEFAULT 0,
    max_lead_days     INTEGER     NOT NULL DEFAULT 0,
    planned_ready_dt  TIMESTAMPTZ,
    actual_ready_dt   TIMESTAMPTZ,                         -- set by material_ready event
    expected_ready_dt TIMESTAMPTZ,
    status            material_status_t NOT NULL DEFAULT 'ordered',
    slip_days         NUMERIC(8,2) NOT NULL DEFAULT 0,
    risk_reason       TEXT,                                -- populated for 'risk'
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE material_status IS 'Procurement readiness per order; one-to-one with order_header.';

-- 5.2 ACTUAL EVENT ------------------------------------------------------
-- Execution screen event log. Optional link to a specific operation.
-- event_qty used by complete/scrap/material_ready; downtime_mins by pause.
CREATE TABLE actual_event (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id          TEXT        NOT NULL UNIQUE,         -- 'EV-001'
    order_id          BIGINT      NOT NULL REFERENCES order_header(id) ON DELETE CASCADE,
    operation_seq     INTEGER,                             -- NULL = order-level
    event_type        event_type_t NOT NULL,
    event_timestamp   TIMESTAMPTZ NOT NULL,
    event_qty         INTEGER     CHECK (event_qty IS NULL OR event_qty >= 0),
    downtime_reason   TEXT,
    downtime_mins     INTEGER     NOT NULL DEFAULT 0 CHECK (downtime_mins >= 0),
    entered_by        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE actual_event IS 'Logged shop-floor & material events; engine recalculates forecast on each.';
CREATE INDEX idx_event_order ON actual_event(order_id);
CREATE INDEX idx_event_type  ON actual_event(event_type);
CREATE INDEX idx_event_ts    ON actual_event(event_timestamp);

-- 5.3 DEVIATION LOG -----------------------------------------------------
-- Auto-regenerated each engine run. Rebuilt wholesale, so no audit cols.
CREATE TABLE deviation_log (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deviation_id        TEXT        NOT NULL,              -- 'DEV-ORD-4312-PROD'
    order_id            BIGINT      NOT NULL REFERENCES order_header(id) ON DELETE CASCADE,
    milestone_name      TEXT        NOT NULL,              -- 'Production end'
    baseline_dt         TIMESTAMPTZ,
    latest_forecast_dt  TIMESTAMPTZ,
    deviation_minutes   NUMERIC(12,2) NOT NULL DEFAULT 0,
    severity            severity_t  NOT NULL,
    root_cause_code     TEXT,                              -- 'Machine downtime'
    action_owner        TEXT,                              -- 'Production supervisor'
    resolution_status   resolution_status_t NOT NULL DEFAULT 'Open',
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE deviation_log IS 'Engine-generated deviations (material & production). Rebuilt every run.';
CREATE INDEX idx_dev_order ON deviation_log(order_id);

-- 5.4 ALERT LOG ---------------------------------------------------------
-- Generated from risk signals; dedup_key keeps ack/closed state across
-- regeneration (UNIQUE so the engine upserts rather than duplicates).
CREATE TABLE alert_log (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alert_id        TEXT        NOT NULL UNIQUE,           -- 'ALT-breach-ORD-4312'
    dedup_key       TEXT        NOT NULL UNIQUE,           -- 'breach-ORD-4312'
    alert_type      alert_type_t NOT NULL,
    order_id        BIGINT      REFERENCES order_header(id) ON DELETE CASCADE,
    title           TEXT        NOT NULL,
    meta            TEXT,
    status          alert_status_t NOT NULL DEFAULT 'open',
    raised_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged_at TIMESTAMPTZ,
    closed_at       TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE alert_log IS 'Role-routed alerts; dedup_key preserves workflow state across recalculation.';
CREATE INDEX idx_alert_order  ON alert_log(order_id);
CREATE INDEX idx_alert_status ON alert_log(status);


-- ---------------------------------------------------------------------
-- 6. DERIVED & HISTORY TABLES
-- ---------------------------------------------------------------------

-- 6.1 CAPACITY LOAD (derived: work-center x day) ------------------------
-- Rebuilt by the finite-capacity engine from order_operation. Pure cache.
CREATE TABLE capacity_load (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    work_center     TEXT        NOT NULL,
    load_date       DATE        NOT NULL,
    available_min   INTEGER     NOT NULL,
    demand_min      NUMERIC(12,2) NOT NULL DEFAULT 0,
    load_pct        NUMERIC(7,2) NOT NULL DEFAULT 0,
    overloaded      BOOLEAN     NOT NULL DEFAULT FALSE,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_capacity_cell UNIQUE (work_center, load_date)
);
COMMENT ON TABLE capacity_load IS 'Derived WC x day loading cache; rebuilt each engine run.';
CREATE INDEX idx_cap_overloaded ON capacity_load(overloaded) WHERE overloaded;

-- 6.2 RESCHEDULE LOG ----------------------------------------------------
-- One row per replan. options stored as JSONB (overtime hrs/window,
-- partial qty, mode) — flexible, queryable, and future-proof.
CREATE TABLE reschedule_log (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id           BIGINT      NOT NULL REFERENCES order_header(id) ON DELETE CASCADE,
    version            INTEGER     NOT NULL,               -- the new schedule version produced
    options            JSONB       NOT NULL DEFAULT '{}',  -- {overtime, overtimeHrs, overtimeFrom/To, partialQty, mode}
    baseline_delivery  TIMESTAMPTZ,
    new_delivery       TIMESTAMPTZ,
    performed_by       TEXT,
    performed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_reschedule UNIQUE (order_id, version)
);
COMMENT ON TABLE reschedule_log IS 'Replan history; options JSONB captures the levers used (overtime window, partial qty, mode).';
CREATE INDEX idx_resched_order ON reschedule_log(order_id);
CREATE INDEX idx_resched_opts  ON reschedule_log USING GIN (options);


-- ---------------------------------------------------------------------
-- 7. updated_at TRIGGERS  (on every table that carries updated_at)
-- ---------------------------------------------------------------------
CREATE TRIGGER trg_plant_upd            BEFORE UPDATE ON plant            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_calendar_upd         BEFORE UPDATE ON plant_calendar   FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_leadtime_upd         BEFORE UPDATE ON lead_time_master FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_threshold_upd        BEFORE UPDATE ON alert_threshold  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_routing_upd          BEFORE UPDATE ON routing          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_routing_op_upd       BEFORE UPDATE ON routing_operation FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_product_upd          BEFORE UPDATE ON product          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_bom_upd              BEFORE UPDATE ON bom_line         FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_order_upd            BEFORE UPDATE ON order_header     FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_material_upd         BEFORE UPDATE ON material_status  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_alert_upd            BEFORE UPDATE ON alert_log        FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ---------------------------------------------------------------------
-- 8. CONVENIENCE VIEWS  (back the dashboard / watchlist without joins in app code)
-- ---------------------------------------------------------------------

-- 8.1 Current schedule per order (latest version only).
CREATE VIEW v_current_schedule AS
SELECT s.*
FROM   planned_schedule s
WHERE  s.is_current;
COMMENT ON VIEW v_current_schedule IS 'The latest schedule version for each order.';

-- 8.2 Order watchlist: order + product + current schedule + material status.
--     Mirrors the dashboard watchlist row (status itself is computed by the
--     engine at runtime; this view assembles the inputs the engine needs).
CREATE VIEW v_order_watchlist AS
SELECT
    o.id                         AS order_pk,
    o.order_id,
    o.customer,
    o.order_qty,
    o.priority,
    o.committed_delivery_date,
    o.sched_mode,
    o.replan_count,
    p.product_id,
    p.name                       AS product_name,
    p.family                     AS product_family,
    pl.plant_code,
    s.baseline_version,
    s.planned_prod_end_dt,
    s.planned_delivery_dt,
    s.buffer_hrs,
    s.schedule_status,
    m.status                     AS material_status,
    m.slip_days                  AS material_slip_days
FROM        order_header o
JOIN        product            p  ON p.id  = o.product_id
LEFT JOIN   plant              pl ON pl.id = o.plant_id
LEFT JOIN   v_current_schedule s  ON s.order_id = o.id
LEFT JOIN   material_status    m  ON m.order_id = o.id;
COMMENT ON VIEW v_order_watchlist IS 'One row per order with product, current schedule and material status joined.';

-- 8.3 Open capacity conflicts (drives the Capacity screen + KPI).
CREATE VIEW v_capacity_conflicts AS
SELECT work_center, load_date, available_min, demand_min, load_pct
FROM   capacity_load
WHERE  overloaded
ORDER  BY work_center, load_date;
COMMENT ON VIEW v_capacity_conflicts IS 'Overloaded work-center days for the Capacity screen and conflicts KPI.';

-- 8.4 Open alerts feed (dashboard + alert badge count).
CREATE VIEW v_open_alerts AS
SELECT a.*, o.order_id AS order_code
FROM   alert_log a
LEFT JOIN order_header o ON o.id = a.order_id
WHERE  a.status = 'open'
ORDER  BY a.raised_at DESC;
COMMENT ON VIEW v_open_alerts IS 'Open alerts with order code for the dashboard feed and badge.';


COMMIT;

-- =====================================================================
--  END OF SCHEMA
--
--  Suggested next steps (Phase 1):
--   * Load reference/master data (plants, calendar, lead times, thresholds,
--     routings + operations, products, BOM) — see plantrack_seed.sql.
--   * Point the FastAPI CRUD layer at these tables.
--   * Port the engine to read order_operation for capacity and write
--     planned_schedule / material_status / deviation_log / alert_log /
--     capacity_load on each recalculation.
-- =====================================================================

-- (See 0002_solve_jobs.sql for the async solve-job tracking table added in Phase 2.)

