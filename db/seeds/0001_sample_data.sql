-- =====================================================================
--  PlanTrack APS — Seed data (0001)
--  Generated from the prototype's sample dataset.
--  Idempotent: safe to run repeatedly (ON CONFLICT DO NOTHING/UPDATE).
--  Run AFTER db/migrations/0001_initial_schema.sql.
-- =====================================================================
BEGIN;

-- Plants -----------------------------------------------------------
INSERT INTO plant(plant_code, plant_name, location) VALUES ('Plant A', 'Pune', 'Pune')
  ON CONFLICT (plant_code) DO NOTHING;
INSERT INTO plant(plant_code, plant_name, location) VALUES ('Plant B', 'Chennai', 'Chennai')
  ON CONFLICT (plant_code) DO NOTHING;

-- Plant calendar (two shifts per plant) ----------------------------
INSERT INTO plant_calendar(plant_id, shift_name, start_time, end_time, available_min, days_active, is_holiday)
  SELECT id, 'Shift A', '06:00', '14:00', 480, 'Mon-Sat', FALSE FROM plant WHERE plant_code='Plant A'
  ON CONFLICT (plant_id, shift_name, holiday_date) DO NOTHING;
INSERT INTO plant_calendar(plant_id, shift_name, start_time, end_time, available_min, days_active, is_holiday)
  SELECT id, 'Shift B', '14:00', '22:00', 480, 'Mon-Sat', FALSE FROM plant WHERE plant_code='Plant A'
  ON CONFLICT (plant_id, shift_name, holiday_date) DO NOTHING;
INSERT INTO plant_calendar(plant_id, shift_name, start_time, end_time, available_min, days_active, is_holiday)
  SELECT id, 'Shift A', '06:00', '14:00', 480, 'Mon-Sat', FALSE FROM plant WHERE plant_code='Plant B'
  ON CONFLICT (plant_id, shift_name, holiday_date) DO NOTHING;
INSERT INTO plant_calendar(plant_id, shift_name, start_time, end_time, available_min, days_active, is_holiday)
  SELECT id, 'Shift B', '14:00', '22:00', 480, 'Mon-Sat', FALSE FROM plant WHERE plant_code='Plant B'
  ON CONFLICT (plant_id, shift_name, holiday_date) DO NOTHING;

-- Lead time master (per family) ------------------------------------
INSERT INTO lead_time_master(product_family, inbound_days, qa_days, packing_days, transport_days, buffer_days)
  VALUES ('Electrical', 4, 2, 1, 3, 1)
  ON CONFLICT (product_family) DO UPDATE SET inbound_days=EXCLUDED.inbound_days;
INSERT INTO lead_time_master(product_family, inbound_days, qa_days, packing_days, transport_days, buffer_days)
  VALUES ('Electronic', 4, 2, 1, 3, 1)
  ON CONFLICT (product_family) DO UPDATE SET inbound_days=EXCLUDED.inbound_days;
INSERT INTO lead_time_master(product_family, inbound_days, qa_days, packing_days, transport_days, buffer_days)
  VALUES ('Hydraulic', 5, 2, 1, 3, 2)
  ON CONFLICT (product_family) DO UPDATE SET inbound_days=EXCLUDED.inbound_days;
INSERT INTO lead_time_master(product_family, inbound_days, qa_days, packing_days, transport_days, buffer_days)
  VALUES ('Mechanical', 3, 1, 1, 2, 1)
  ON CONFLICT (product_family) DO UPDATE SET inbound_days=EXCLUDED.inbound_days;

-- Alert thresholds -------------------------------------------------
INSERT INTO alert_threshold(threshold_key, label, value, unit, fires_when)
  VALUES ('start_miss_min', 'Start miss escalation', 30, 'min', 'Op start later than planned by this much -> supervisor')
  ON CONFLICT (threshold_key) DO UPDATE SET value=EXCLUDED.value;
INSERT INTO alert_threshold(threshold_key, label, value, unit, fires_when)
  VALUES ('run_rate_pct', 'Run-rate floor', 90, '%', 'Actual run rate below this % of required -> line manager')
  ON CONFLICT (threshold_key) DO UPDATE SET value=EXCLUDED.value;
INSERT INTO alert_threshold(threshold_key, label, value, unit, fires_when)
  VALUES ('risk_slip_hrs', 'At-risk slip', 0.5, 'hrs', 'Forecast slip beyond this -> order flagged At risk')
  ON CONFLICT (threshold_key) DO UPDATE SET value=EXCLUDED.value;
INSERT INTO alert_threshold(threshold_key, label, value, unit, fires_when)
  VALUES ('delay_slip_hrs', 'Delayed slip', 2, 'hrs', 'Forecast slip beyond this -> order flagged Delayed')
  ON CONFLICT (threshold_key) DO UPDATE SET value=EXCLUDED.value;
INSERT INTO alert_threshold(threshold_key, label, value, unit, fires_when)
  VALUES ('crit_slip_hrs', 'Critical slip', 8, 'hrs', 'Forecast slip beyond this -> order flagged Critical')
  ON CONFLICT (threshold_key) DO UPDATE SET value=EXCLUDED.value;
INSERT INTO alert_threshold(threshold_key, label, value, unit, fires_when)
  VALUES ('buffer_watch_pct', 'Buffer watch', 60, '%', 'Remaining buffer below this % -> Watch')
  ON CONFLICT (threshold_key) DO UPDATE SET value=EXCLUDED.value;
INSERT INTO alert_threshold(threshold_key, label, value, unit, fires_when)
  VALUES ('buffer_crit_pct', 'Buffer critical', 20, '%', 'Remaining buffer below this % -> Critical')
  ON CONFLICT (threshold_key) DO UPDATE SET value=EXCLUDED.value;
INSERT INTO alert_threshold(threshold_key, label, value, unit, fires_when)
  VALUES ('silent_miss_min', 'Silent start miss', 45, 'min', 'No start event this long after planned start -> silent miss')
  ON CONFLICT (threshold_key) DO UPDATE SET value=EXCLUDED.value;
INSERT INTO alert_threshold(threshold_key, label, value, unit, fires_when)
  VALUES ('cap_util_warn', 'Capacity warn', 85, '%', 'Work-center daily load above this % -> warn')
  ON CONFLICT (threshold_key) DO UPDATE SET value=EXCLUDED.value;
INSERT INTO alert_threshold(threshold_key, label, value, unit, fires_when)
  VALUES ('mat_risk_window_days', 'Material risk window', 3, 'days', 'Material due within this many days, unconfirmed -> at risk')
  ON CONFLICT (threshold_key) DO UPDATE SET value=EXCLUDED.value;
INSERT INTO alert_threshold(threshold_key, label, value, unit, fires_when)
  VALUES ('mat_staging_days', 'Material staging lead', 1, 'days', 'Backward mode: material ready this many days before start')
  ON CONFLICT (threshold_key) DO UPDATE SET value=EXCLUDED.value;

-- Routings ---------------------------------------------------------
INSERT INTO routing(route_id, description) VALUES ('R-STD-01', 'R-STD-01 process flow')
  ON CONFLICT (route_id) DO NOTHING;
INSERT INTO routing(route_id, description) VALUES ('R-STD-02', 'R-STD-02 process flow')
  ON CONFLICT (route_id) DO NOTHING;
INSERT INTO routing(route_id, description) VALUES ('R-ELEC-01', 'R-ELEC-01 process flow')
  ON CONFLICT (route_id) DO NOTHING;
INSERT INTO routing(route_id, description) VALUES ('R-HYD-01', 'R-HYD-01 process flow')
  ON CONFLICT (route_id) DO NOTHING;

-- Routing operations -----------------------------------------------
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 10, 'Material prep', 60, 0.5, 30, 15, NULL, NULL FROM routing WHERE route_id='R-STD-01'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 20, 'Machining', 90, 1.2, 30, 15, 10, NULL FROM routing WHERE route_id='R-STD-01'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 30, 'Assembly', 45, 2.0, 20, 10, 20, NULL FROM routing WHERE route_id='R-STD-01'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 40, 'QC inspection', 30, 0.3, 15, 10, 30, NULL FROM routing WHERE route_id='R-STD-01'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 50, 'Paint / finish', 45, 0.4, 20, 15, 30, 'G1' FROM routing WHERE route_id='R-STD-01'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 60, 'Packing', 15, 0.2, 10, 5, 40, NULL FROM routing WHERE route_id='R-STD-01'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 10, 'Casting', 120, 1.5, 60, 20, NULL, NULL FROM routing WHERE route_id='R-STD-02'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 20, 'Machining', 90, 2.0, 30, 15, 10, NULL FROM routing WHERE route_id='R-STD-02'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 30, 'Assembly', 60, 3.0, 20, 10, 20, NULL FROM routing WHERE route_id='R-STD-02'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 40, 'QC inspection', 30, 0.5, 15, 10, 30, NULL FROM routing WHERE route_id='R-STD-02'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 10, 'PCB assembly', 60, 3.0, 30, 10, NULL, NULL FROM routing WHERE route_id='R-ELEC-01'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 20, 'Wiring', 30, 2.5, 20, 10, 10, 'G1' FROM routing WHERE route_id='R-ELEC-01'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 30, 'Firmware load', 20, 1.0, 15, 5, 10, 'G1' FROM routing WHERE route_id='R-ELEC-01'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 40, 'Testing', 45, 1.0, 20, 10, 20, NULL FROM routing WHERE route_id='R-ELEC-01'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 50, 'Packing', 15, 0.2, 10, 5, 40, NULL FROM routing WHERE route_id='R-ELEC-01'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 10, 'Component prep', 90, 2.0, 45, 20, NULL, NULL FROM routing WHERE route_id='R-HYD-01'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 20, 'Hyd assembly', 120, 4.0, 30, 20, 10, NULL FROM routing WHERE route_id='R-HYD-01'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 30, 'Pressure test', 60, 1.0, 20, 15, 20, NULL FROM routing WHERE route_id='R-HYD-01'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;
INSERT INTO routing_operation(routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min, predecessor_seq, parallel_group)
  SELECT id, 40, 'QC & pack', 30, 0.5, 10, 10, 30, NULL FROM routing WHERE route_id='R-HYD-01'
  ON CONFLICT (routing_id, operation_seq) DO NOTHING;

-- Products ---------------------------------------------------------
INSERT INTO product(product_id, name, family, routing_id)
  SELECT 'P-1001', 'Gear Housing A2', 'Mechanical', r.id FROM routing r WHERE r.route_id='R-STD-01'
  ON CONFLICT (product_id) DO NOTHING;
INSERT INTO product(product_id, name, family, routing_id)
  SELECT 'P-1002', 'Bracket Set 7', 'Mechanical', r.id FROM routing r WHERE r.route_id='R-STD-02'
  ON CONFLICT (product_id) DO NOTHING;
INSERT INTO product(product_id, name, family, routing_id)
  SELECT 'P-1003', 'Motor Shaft XL', 'Mechanical', r.id FROM routing r WHERE r.route_id='R-STD-01'
  ON CONFLICT (product_id) DO NOTHING;
INSERT INTO product(product_id, name, family, routing_id)
  SELECT 'P-1004', 'Valve Assembly', 'Hydraulic', r.id FROM routing r WHERE r.route_id='R-HYD-01'
  ON CONFLICT (product_id) DO NOTHING;
INSERT INTO product(product_id, name, family, routing_id)
  SELECT 'P-1005', 'Control Panel C', 'Electronic', r.id FROM routing r WHERE r.route_id='R-ELEC-01'
  ON CONFLICT (product_id) DO NOTHING;
INSERT INTO product(product_id, name, family, routing_id)
  SELECT 'P-1006', 'Frame Assembly', 'Mechanical', r.id FROM routing r WHERE r.route_id='R-STD-02'
  ON CONFLICT (product_id) DO NOTHING;
INSERT INTO product(product_id, name, family, routing_id)
  SELECT 'P-1007', 'Bearing Kit Pro', 'Mechanical', r.id FROM routing r WHERE r.route_id='R-STD-01'
  ON CONFLICT (product_id) DO NOTHING;
INSERT INTO product(product_id, name, family, routing_id)
  SELECT 'P-1008', 'PCB Module X3', 'Electrical', r.id FROM routing r WHERE r.route_id='R-ELEC-01'
  ON CONFLICT (product_id) DO NOTHING;
INSERT INTO product(product_id, name, family, routing_id)
  SELECT 'P-1009', 'Hydraulic Pump V2', 'Hydraulic', r.id FROM routing r WHERE r.route_id='R-HYD-01'
  ON CONFLICT (product_id) DO NOTHING;
INSERT INTO product(product_id, name, family, routing_id)
  SELECT 'P-1010', 'Shaft Coupling 3L', 'Mechanical', r.id FROM routing r WHERE r.route_id='R-STD-01'
  ON CONFLICT (product_id) DO NOTHING;

-- Bill of materials ------------------------------------------------
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'Cast iron blank', 1.2, 'kg', 'SteelCo', 5 FROM product WHERE product_id='P-1001'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'Bearing race', 2, 'pcs', 'BearingPlus', 7 FROM product WHERE product_id='P-1001'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'Seal kit', 1, 'set', 'SealMaster', 3 FROM product WHERE product_id='P-1001'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'Steel sheet 3mm', 0.8, 'kg', 'SteelCo', 4 FROM product WHERE product_id='P-1002'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'Mounting bolts', 6, 'pcs', 'FastenAll', 2 FROM product WHERE product_id='P-1002'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'Alloy steel rod', 2.5, 'kg', 'AlloyTech', 6 FROM product WHERE product_id='P-1003'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'Valve body casting', 1, 'pcs', 'CastWorks', 8 FROM product WHERE product_id='P-1004'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'Hydraulic seal', 4, 'pcs', 'SealMaster', 5 FROM product WHERE product_id='P-1004'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'PCB board', 1, 'pcs', 'CircuitFab', 10 FROM product WHERE product_id='P-1005'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'Enclosure', 1, 'pcs', 'BoxMakers', 4 FROM product WHERE product_id='P-1005'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'Connector set', 1, 'set', 'CircuitFab', 6 FROM product WHERE product_id='P-1005'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'Steel tube', 3, 'm', 'TubeWorks', 5 FROM product WHERE product_id='P-1006'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'Bearing race', 4, 'pcs', 'BearingPlus', 7 FROM product WHERE product_id='P-1007'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'Grease pack', 1, 'set', 'LubeCo', 2 FROM product WHERE product_id='P-1007'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'PCB board', 1, 'pcs', 'CircuitFab', 10 FROM product WHERE product_id='P-1008'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'Copper wire', 0.5, 'kg', 'WireCo', 3 FROM product WHERE product_id='P-1008'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'Pump casting', 1, 'pcs', 'CastWorks', 9 FROM product WHERE product_id='P-1009'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'Hydraulic seal', 6, 'pcs', 'SealMaster', 5 FROM product WHERE product_id='P-1009'
  ON CONFLICT DO NOTHING;
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
  SELECT id, 'Alloy steel rod', 1.5, 'kg', 'AlloyTech', 6 FROM product WHERE product_id='P-1010'
  ON CONFLICT DO NOTHING;

-- Orders (dates relative to a fixed seed date 2026-06-30) ----------
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date, committed_delivery_date, priority, plant_id, sched_mode)
  SELECT 'ORD-4312', p.id, 'BMW AG', 500, '2026-06-18', '2026-07-18', 'HIGH', pl.id, 'backward'
  FROM product p, plant pl WHERE p.product_id='P-1001' AND pl.plant_code='Plant A'
  ON CONFLICT (order_id) DO NOTHING;
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date, committed_delivery_date, priority, plant_id, sched_mode)
  SELECT 'ORD-4318', p.id, 'Volvo DE', 250, '2026-06-20', '2026-07-14', 'HIGH', pl.id, 'backward'
  FROM product p, plant pl WHERE p.product_id='P-1002' AND pl.plant_code='Plant B'
  ON CONFLICT (order_id) DO NOTHING;
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date, committed_delivery_date, priority, plant_id, sched_mode)
  SELECT 'ORD-4305', p.id, 'Ford EU', 800, '2026-06-16', '2026-07-22', 'MED', pl.id, 'backward'
  FROM product p, plant pl WHERE p.product_id='P-1003' AND pl.plant_code='Plant A'
  ON CONFLICT (order_id) DO NOTHING;
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date, committed_delivery_date, priority, plant_id, sched_mode)
  SELECT 'ORD-4299', p.id, 'Bosch GmbH', 120, '2026-06-22', '2026-07-26', 'MED', pl.id, 'backward'
  FROM product p, plant pl WHERE p.product_id='P-1004' AND pl.plant_code='Plant B'
  ON CONFLICT (order_id) DO NOTHING;
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date, committed_delivery_date, priority, plant_id, sched_mode)
  SELECT 'ORD-4287', p.id, 'Siemens AG', 60, '2026-06-24', '2026-07-30', 'LOW', pl.id, 'backward'
  FROM product p, plant pl WHERE p.product_id='P-1005' AND pl.plant_code='Plant A'
  ON CONFLICT (order_id) DO NOTHING;
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date, committed_delivery_date, priority, plant_id, sched_mode)
  SELECT 'ORD-4281', p.id, 'GE Aviation', 200, '2026-06-15', '2026-07-12', 'HIGH', pl.id, 'backward'
  FROM product p, plant pl WHERE p.product_id='P-1006' AND pl.plant_code='Plant B'
  ON CONFLICT (order_id) DO NOTHING;
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date, committed_delivery_date, priority, plant_id, sched_mode)
  SELECT 'ORD-4275', p.id, 'SKF Nordic', 1000, '2026-06-25', '2026-08-03', 'LOW', pl.id, 'backward'
  FROM product p, plant pl WHERE p.product_id='P-1007' AND pl.plant_code='Plant A'
  ON CONFLICT (order_id) DO NOTHING;
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date, committed_delivery_date, priority, plant_id, sched_mode)
  SELECT 'ORD-4268', p.id, 'Honeywell', 150, '2026-06-21', '2026-07-28', 'MED', pl.id, 'backward'
  FROM product p, plant pl WHERE p.product_id='P-1008' AND pl.plant_code='Plant A'
  ON CONFLICT (order_id) DO NOTHING;
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date, committed_delivery_date, priority, plant_id, sched_mode)
  SELECT 'ORD-4255', p.id, 'Caterpillar', 80, '2026-06-19', '2026-07-20', 'HIGH', pl.id, 'backward'
  FROM product p, plant pl WHERE p.product_id='P-1009' AND pl.plant_code='Plant B'
  ON CONFLICT (order_id) DO NOTHING;
INSERT INTO order_header(order_id, product_id, customer, order_qty, order_date, committed_delivery_date, priority, plant_id, sched_mode)
  SELECT 'ORD-4243', p.id, 'ABB Ltd', 300, '2026-06-23', '2026-07-30', 'MED', pl.id, 'backward'
  FROM product p, plant pl WHERE p.product_id='P-1010' AND pl.plant_code='Plant A'
  ON CONFLICT (order_id) DO NOTHING;

COMMIT;