-- Periodic KPI snapshots, so the dashboard can show trend deltas ("vs
-- yesterday") and a "since you last checked" digest instead of only ever
-- showing a single point-in-time number.
BEGIN;

CREATE TABLE dashboard_snapshot (
    id BIGSERIAL PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    schedule_adherence_pct INT,
    on_time_delivery_pct INT,
    orders_at_risk INT,
    delayed_critical INT,
    unconfirmed INT,
    material_at_risk INT,
    capacity_conflicts INT,
    delayed_critical_order_ids JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX idx_dashboard_snapshot_captured_at ON dashboard_snapshot (captured_at);

COMMIT;
