-- =====================================================================
-- DEMO ORDERS — 10 orders, each fabricated to demonstrate one PlanTrack
-- capability. ALL DATES ARE RELATIVE TO THE LOAD MOMENT (CURRENT_DATE),
-- so the "days until due" tensions each scenario depends on hold no
-- matter when this script is run.
--
-- Calibrated against real solver behaviour for this shop (one plant, one
-- 10h shift, plasma->weld->CNC->coat->QC): a solo order finishes ~2-4
-- days out; QC/NDT hold alone is 480-600 min. Offsets below are chosen
-- so each scenario lands correctly in the FULL 9-order solve (subset
-- behaviour differs from full-fleet contention — everything here is
-- tuned against the whole fleet).
--
--   9001  A  Healthy baseline           - due +14d, comfortably on time
--   9002  D  Unscheduled ("before")      - no schedule row; solve live
--   9003  E  Material late               - order_date -19d, 12d lead -> ready 7d ago
--   9004  G  Capacity breach             - contends for Welding w/ 9009/9010
--   9005  H  Quiet-day contrast          - LOW, generous due, lands on a light day
--   9006  I  Delayed, +4h recovers it    - due +2d; late plainly, on-time w/ +4h OT
--   9007  J  Overtime can't save it      - PV, material not ready until +11d
--   9008  K  Sandbox tradeoffs           - LOW, generous due
--   9009  L  Priority contention (HIGH)  - protected; due +9d
--   9010  L  Priority contention (LOW)   - slips; due +4d (same as 9004)
-- =====================================================================
BEGIN;

-- 9001: A — Healthy baseline (due +14d; ordered today so material fine)
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9001', p.id, 'Kirloskar Pumps Ltd', 40, CURRENT_DATE,
       CURRENT_DATE + 14, 'MED', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-BRK-100' AND pl.plant_code='PLANT-1';

-- 9002: D — Unscheduled "before" state (NOT solved in seed; solve it live)
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9002', p.id, 'Godrej Infrastructure', 25, CURRENT_DATE,
       CURRENT_DATE + 9, 'MED', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-FRM-200' AND pl.plant_code='PLANT-1';

-- 9003: E — Material late. order_date 19 days ago; P-VES-500 max BOM lead
-- is 12 days -> planned_ready = 7 days ago, no arrival -> 'late'. Due date
-- generous so THIS order's story is purely material, not schedule.
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9003', p.id, 'Bharat Petroleum Corp', 6, CURRENT_DATE - 19,
       CURRENT_DATE + 27, 'HIGH', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-VES-500' AND pl.plant_code='PLANT-1';

-- 9004: G — Capacity breach. Same product/window as 9009/9010, all three
-- contend for Welding at once, pushing that day over 600 min. Due +4d.
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9004', p.id, 'Tata Projects', 30, CURRENT_DATE,
       CURRENT_DATE + 4, 'MED', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-CHS-400' AND pl.plant_code='PLANT-1';

-- 9005: H — Quiet-day contrast. LOW, small qty, generous due -> solver
-- parks it on a lighter day; a visibly light heatmap cell.
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9005', p.id, 'Larsen Engineering Works', 8, CURRENT_DATE,
       CURRENT_DATE + 16, 'LOW', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-PLT-300' AND pl.plant_code='PLANT-1';

-- 9006: I — Delayed but cleanly recoverable. Due +2d: plain schedule lands
-- late, +4h/day overtime recovers it fully (verified via recovery dry-run).
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9006', p.id, 'Honeywell Automation', 60, CURRENT_DATE,
       CURRENT_DATE + 2, 'HIGH', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-FRM-200' AND pl.plant_code='PLANT-1';

-- 9007: J — Overtime can't save it (material-bound). PV product ordered
-- 1 day ago; 12-day plate lead -> material not ready for ~11 more days.
-- Due +9d is before material can even arrive, so no machine overtime
-- helps -- the honest "overtime won't fix this" recommendation.
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9007', p.id, 'Reliance Engineering', 4, CURRENT_DATE - 1,
       CURRENT_DATE + 9, 'HIGH', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-VES-500' AND pl.plant_code='PLANT-1';

-- 9008: K — Sandbox tradeoffs. LOW, generous due; safe to exclude/cut qty
-- in a what-if without real consequence.
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9008', p.id, 'Local Fabrication Co-op', 15, CURRENT_DATE,
       CURRENT_DATE + 23, 'LOW', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-PLT-300' AND pl.plant_code='PLANT-1';

-- 9009: L — Priority contention (HIGH). Competes with 9004/9010 for
-- Welding; HIGH + due +9d -> protected, stays on time.
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9009', p.id, 'BHEL — Boiler Division', 20, CURRENT_DATE,
       CURRENT_DATE + 9, 'HIGH', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-CHS-400' AND pl.plant_code='PLANT-1';

-- 9010: L — Priority contention (LOW) + audit-trail order. Same product &
-- due (+4d) as 9004; LOW priority -> this is the one that slips. Also the
-- order we run a live recovery on so audit_log gets a real actor+action.
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9010', p.id, 'Small Metalworks Pvt Ltd', 20, CURRENT_DATE,
       CURRENT_DATE + 4, 'LOW', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-CHS-400' AND pl.plant_code='PLANT-1';

COMMIT;
