-- =====================================================================
-- DEMO ORDERS - 10 orders, each demonstrating one PlanTrack capability.
-- Dates are CURRENT_DATE-relative (reset-proof) AND use WIDE MARGINS so
-- each scenario lands reliably regardless of solver variance or which
-- weekday the reset happens on. Healthy orders are emphatically safe;
-- late orders are emphatically late.
--
--   9001  A  Healthy baseline           - due +21d, never accidentally late
--   9002  D  Unscheduled ("before")      - no schedule row; solve live
--   9003  E  Material late               - order -22d, 12d lead -> ready 10d ago
--   9004  G  Capacity breach + late      - due +1d, always late (contention)
--   9005  H  Quiet-day contrast          - LOW, due +25d, always safe
--   9006  I  Delayed but +4h recovers    - due +4d: reliably late (~11h), +4h OT recovers
--   9007  J  Overtime can't save it      - due +6d, material not ready ~9 working days
--   9008  K  Sandbox tradeoffs           - LOW, due +28d, always safe
--   9009  L  Priority contention (HIGH)  - due +12d, protected -> on time
--   9010  L  Priority contention (LOW)   - due +1d, LOW -> always slips
-- =====================================================================
BEGIN;

-- 9001: A - Healthy baseline. Due +21d: far beyond its ~2-day natural
-- finish, so on time on every solve. Ordered today -> material fine.
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9001', p.id, 'Kirloskar Pumps Ltd', 40, CURRENT_DATE,
       CURRENT_DATE + 21, 'MED', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-BRK-100' AND pl.plant_code='PLANT-1';

-- 9002: D - Unscheduled "before" state (NOT solved in seed; solve live).
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9002', p.id, 'Godrej Infrastructure', 25, CURRENT_DATE,
       CURRENT_DATE + 14, 'MED', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-FRM-200' AND pl.plant_code='PLANT-1';

-- 9003: E - Material late. order_date 22 days ago; P-VES-500 max BOM lead
-- 12 days -> material was due ~10 days ago, unconfirmed -> emphatically
-- 'late'. Due +27d so THIS order's story is purely material, never schedule.
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9003', p.id, 'Bharat Petroleum Corp', 6, CURRENT_DATE - 22,
       CURRENT_DATE + 27, 'HIGH', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-VES-500' AND pl.plant_code='PLANT-1';

-- 9004: G - Capacity breach + reliably late. Due +1d is far inside the
-- ~2-4 day the shop physically needs, so it's late on every solve, and it
-- piles onto Welding with 9009/9010 -> a red heatmap cell.
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9004', p.id, 'Tata Projects', 30, CURRENT_DATE,
       CURRENT_DATE + 1, 'MED', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-CHS-400' AND pl.plant_code='PLANT-1';

-- 9005: H - Quiet-day contrast. LOW, small qty, due +25d -> always safe,
-- parked on a light day for the heatmap contrast.
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9005', p.id, 'Larsen Engineering Works', 8, CURRENT_DATE,
       CURRENT_DATE + 25, 'LOW', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-PLT-300' AND pl.plant_code='PLANT-1';

-- 9006: I - Delayed but cleanly recoverable. Due +2d: reliably late on the
-- plain solve, but small enough gap that +4h/day overtime recovers it.
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9006', p.id, 'Honeywell Automation', 60, CURRENT_DATE,
       CURRENT_DATE + 4, 'HIGH', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-FRM-200' AND pl.plant_code='PLANT-1';

-- 9007: J - Overtime can't save it (material-bound). PV product ordered
-- yesterday; 12-day plate lead -> material not ready ~11 more days. Due +9d
-- is before material can arrive, so no machine overtime helps.
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9007', p.id, 'Reliance Engineering', 4, CURRENT_DATE - 1,
       CURRENT_DATE + 6, 'HIGH', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-VES-500' AND pl.plant_code='PLANT-1';

-- 9008: K - Sandbox tradeoffs. LOW, due +28d -> always safe; the natural
-- candidate to exclude/cut qty in a what-if.
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9008', p.id, 'Local Fabrication Co-op', 15, CURRENT_DATE,
       CURRENT_DATE + 28, 'LOW', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-PLT-300' AND pl.plant_code='PLANT-1';

-- 9009: L - Priority contention (HIGH). Competes with 9004/9010 for
-- Welding; HIGH + due +12d -> comfortably protected, on time every solve.
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9009', p.id, 'BHEL - Boiler Division', 20, CURRENT_DATE,
       CURRENT_DATE + 12, 'HIGH', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-CHS-400' AND pl.plant_code='PLANT-1';

-- 9010: L - Priority contention (LOW) + audit-trail order. Same product as
-- 9004/9009 but LOW priority and due +1d -> always the one that slips.
-- Also the order to run a live recovery on for the audit trail.
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-9010', p.id, 'Small Metalworks Pvt Ltd', 20, CURRENT_DATE,
       CURRENT_DATE + 1, 'LOW', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P-CHS-400' AND pl.plant_code='PLANT-1';

COMMIT;
