-- =====================================================================
-- DEMO RESET — wipe all orders and everything CASCADE-tied to them,
-- plus master data we're replacing (plants/calendar/routings/products).
-- Users (app_user) are NOT touched — logins stay intact.
-- =====================================================================
BEGIN;

-- Orders cascade-delete: planned_schedule, order_operation, material_status,
-- actual_event, deviation_log, alert_log (order-linked), reschedule_log.
DELETE FROM order_header;

-- Wipe capacity/solve history tied to the old dataset.
DELETE FROM capacity_load;
DELETE FROM solve_job;

-- Wipe old products/BOM/routings/plants/calendar/lead-times — we're
-- replacing the whole shop model, not just the orders.
DELETE FROM bom_line;
DELETE FROM product;
DELETE FROM routing_operation;
DELETE FROM changeover_matrix;
DELETE FROM routing;
DELETE FROM plant_calendar;
DELETE FROM lead_time_master;
DELETE FROM plant;

COMMIT;
