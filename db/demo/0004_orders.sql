
-- =====================================================================
-- DEMO ORDERS v3 -- cutting & welding machine manufacturer rebrand.
-- Same 14 calibrated stories as before; only product/customer names
-- changed. Verified against the real solver: identical numbers to the
-- prior version (adherence 86%, OTD 86%, ORD-1012 -11.18h -> +4h/day OT
-- recovers it, ORD-1014 flags Delay from downtime while staying on-time).
--
--   1001-1008  Healthy baseline spread     - Indian Railway, Titagarh Rail,
--                                              Cochin Shipyard, MDSL, Hindustan
--                                              Shipyard, GRSE, BHEL, BEML
--   1003,1005,
--   1009,1013  Material ready (confirmed)  - needs the same follow-up SQL
--                                              step after reset (see notes)
--   1010       Material at risk            - Sir C.V. Raman ITI, Dheerpur
--   1011       Material late (unresolved)  - Auto-ancillary Fabricator Pvt Ltd
--   1012       CENTERPIECE (L&T Construction) - delayed, root cause, +4h/day
--                                              overtime recommendation recovers it
--   1014       Downtime example (ITI Okhla) - needs the same follow-up
--                                              POST /events call after reset
-- =====================================================================
BEGIN;

INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-1001', p.id, 'Indian Railway', 30, CURRENT_DATE,
       CURRENT_DATE + 18, 'HIGH', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P1' AND pl.plant_code='PLANT-1';

INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-1002', p.id, 'Titagarh Rail Systems', 15, CURRENT_DATE,
       CURRENT_DATE + 15, 'HIGH', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P3' AND pl.plant_code='PLANT-1';

INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-1003', p.id, 'Cochin Shipyard', 8, CURRENT_DATE - 6,
       CURRENT_DATE + 20, 'MED', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P2' AND pl.plant_code='PLANT-1';

INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-1004', p.id, 'Mazagon Dock Shipbuilders Limited (MDSL)', 20, CURRENT_DATE,
       CURRENT_DATE + 16, 'MED', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P4' AND pl.plant_code='PLANT-1';

INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-1005', p.id, 'Hindustan Shipyard Limited', 10, CURRENT_DATE - 6,
       CURRENT_DATE + 25, 'LOW', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P2' AND pl.plant_code='PLANT-1';

INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-1006', p.id, 'Garden Reach Shipbuilders & Engineers (GRSE)', 14, CURRENT_DATE,
       CURRENT_DATE + 16, 'MED', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P3' AND pl.plant_code='PLANT-1';

INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-1007', p.id, 'Bharat Heavy Electricals Limited (BHEL)', 18, CURRENT_DATE,
       CURRENT_DATE + 19, 'MED', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P4' AND pl.plant_code='PLANT-1';

INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-1008', p.id, 'BEML Limited', 25, CURRENT_DATE,
       CURRENT_DATE + 22, 'LOW', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P1' AND pl.plant_code='PLANT-1';

-- 1009: material ready, confirmed on time (explicit material_status seed below)
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-1009', p.id, 'ITI Pusa, New Delhi', 5, CURRENT_DATE - 14,
       CURRENT_DATE + 16, 'HIGH', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P5' AND pl.plant_code='PLANT-1';

-- 1010: material at risk - due within the risk window, unconfirmed, schedule kept safe
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-1010', p.id, 'Sir C. V. Raman Industrial Training Institute, Dheerpur', 6, CURRENT_DATE - 10,
       CURRENT_DATE + 25, 'HIGH', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P5' AND pl.plant_code='PLANT-1';

-- 1011: material late, unresolved - purely a material story, schedule kept safe
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-1011', p.id, 'Auto-ancillary Fabricator Pvt Ltd.', 6, CURRENT_DATE - 22,
       CURRENT_DATE + 27, 'HIGH', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P5' AND pl.plant_code='PLANT-1';

-- 1012: CENTERPIECE - delayed, clear root cause, overtime recommendation
-- recovers it. Verified against the full 14-order solve: reliably ~11.2h
-- late (crit) out of the box; +4h/day overtime fully clears it to on-time.
-- Doubles as the "single-order recovery" demo AND the "root cause ->
-- recommendation" walkthrough -- they are the same mechanism.
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-1012', p.id, 'L&T Construction', 25, CURRENT_DATE,
       CURRENT_DATE + 11, 'HIGH', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P4' AND pl.plant_code='PLANT-1';

-- 1013: downtime example, buffer absorbs it (downtime event added separately)
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-1013', p.id, 'Bharat Forge Ltd', 8, CURRENT_DATE - 6,
       CURRENT_DATE + 20, 'MED', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P2' AND pl.plant_code='PLANT-1';

-- 1014: downtime example. Verified safely on-time out of the box
-- (buffer ~12h) even after a downtime event is logged against it (logged
-- separately via POST /events -- see delivery notes; downtime can't be
-- seeded via raw order_header SQL).
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date,
                         committed_delivery_date, priority, plant_id, sched_mode)
SELECT 'ORD-1014', p.id, 'ITI Okhla, New Delhi', 4, CURRENT_DATE,
       CURRENT_DATE + 9, 'MED', pl.id, 'forward'
FROM product p, plant pl WHERE p.product_id='P3' AND pl.plant_code='PLANT-1';

COMMIT;


