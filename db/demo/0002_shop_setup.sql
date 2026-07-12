-- =====================================================================
-- DEMO SHOP SETUP - one plant, one 10-hour shift, plasma/welding/CNC/
-- coating/QC routing for a metal-fabrication (plasma cutting, welding,
-- coating) shop.
-- =====================================================================
BEGIN;

-- ---- Plant: single factory ----
INSERT INTO plant(plant_code, plant_name, location)
VALUES ('PLANT-1', 'Apex Fabrication Works', 'Pune');

-- One shift, 10:00 to 20:00 = 600 available minutes/day, Mon-Sat.
INSERT INTO plant_calendar(plant_id, shift_name, start_time, end_time, available_min, days_active, is_holiday)
SELECT id, 'Day shift', '10:00', '20:00', 600, 'Mon-Sat', false FROM plant WHERE plant_code='PLANT-1';

-- ---- Lead-time master (by product family) ----
INSERT INTO lead_time_master(product_family, inbound_days, qa_days, packing_days, transport_days, buffer_days)
VALUES ('Structural Steel', 3, 1, 1, 2, 1),
       ('Pressure Vessel',  6, 2, 1, 2, 2);

-- ---- Routing: PLASMA -> WELD -> CNC -> COATING -> QC ----
-- One shared routing used by all demo products; operations carry
-- eligible_work_centers (Welding step can run on WELD-1 or WELD-2) and
-- setup_family (used for sequence-dependent changeover between families).
INSERT INTO routing(route_id, description) VALUES ('R-FAB-STD', 'Plasma cut -> Weld -> CNC -> Coat -> QC');

INSERT INTO routing_operation
  (routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min,
   predecessor_seq, eligible_work_centers, setup_family)
SELECT id, 10, 'Plasma Cutting', 30, 4.0, 20, 15, NULL, NULL, 'PLATE'
FROM routing WHERE route_id='R-FAB-STD';

INSERT INTO routing_operation
  (routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min,
   predecessor_seq, eligible_work_centers, setup_family)
SELECT id, 20, 'Welding', 45, 12.0, 30, 20, 10, 'Welding,Welding-2', 'WELD-STRUCT'
FROM routing WHERE route_id='R-FAB-STD';

INSERT INTO routing_operation
  (routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min,
   predecessor_seq, eligible_work_centers, setup_family)
SELECT id, 30, 'CNC Machining', 40, 6.0, 20, 15, 20, NULL, 'CNC-STD'
FROM routing WHERE route_id='R-FAB-STD';

INSERT INTO routing_operation
  (routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min,
   predecessor_seq, eligible_work_centers, setup_family)
SELECT id, 40, 'Coating', 25, 3.0, 15, 10, 30, NULL, 'COAT-POWDER'
FROM routing WHERE route_id='R-FAB-STD';

-- QC/Inspection: deliberately long - weld cooldown hold + visual + dye-
-- penetrant + sampled UT, per real fabrication-shop NDT practice.
INSERT INTO routing_operation
  (routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min,
   predecessor_seq, eligible_work_centers, setup_family)
SELECT id, 50, 'QC Inspection', 480, 2.0, 60, 10, 40, NULL, 'QC-NDT'
FROM routing WHERE route_id='R-FAB-STD';

-- A second routing for the pressure-vessel-style product (order 9007),
-- identical stages but heavier QC (stricter NDT hold per code) and a
-- deliberately long material lead time (used for the "overtime can't
-- save it" scenario).
INSERT INTO routing(route_id, description) VALUES ('R-FAB-PV', 'Plasma cut -> Weld -> CNC -> Coat -> QC (pressure-rated, strict NDT)');

INSERT INTO routing_operation
  (routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min,
   predecessor_seq, eligible_work_centers, setup_family)
SELECT id, 10, 'Plasma Cutting', 30, 4.5, 20, 15, NULL, NULL, 'PLATE'
FROM routing WHERE route_id='R-FAB-PV';

INSERT INTO routing_operation
  (routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min,
   predecessor_seq, eligible_work_centers, setup_family)
SELECT id, 20, 'Welding', 45, 14.0, 30, 20, 10, 'Welding,Welding-2', 'WELD-PV'
FROM routing WHERE route_id='R-FAB-PV';

INSERT INTO routing_operation
  (routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min,
   predecessor_seq, eligible_work_centers, setup_family)
SELECT id, 30, 'CNC Machining', 40, 7.0, 20, 15, 20, NULL, 'CNC-STD'
FROM routing WHERE route_id='R-FAB-PV';

INSERT INTO routing_operation
  (routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min,
   predecessor_seq, eligible_work_centers, setup_family)
SELECT id, 40, 'Coating', 25, 3.5, 15, 10, 30, NULL, 'COAT-POWDER'
FROM routing WHERE route_id='R-FAB-PV';

-- Pressure-vessel NDT hold: 48h post-weld cooldown per code (600 min/day
-- shift => this alone spans multiple working days), realistic per AWS/DNV
-- guidance on delayed-cracking inspection windows.
INSERT INTO routing_operation
  (routing_id, operation_seq, work_center, setup_min, run_per_unit_min, queue_min, move_min,
   predecessor_seq, eligible_work_centers, setup_family)
SELECT id, 50, 'QC Inspection', 600, 3.0, 60, 10, 40, NULL, 'QC-NDT-STRICT'
FROM routing WHERE route_id='R-FAB-PV';

-- ---- Sequence-dependent changeover: switching setup families on the same
-- machine costs extra setup time (e.g. Welding switching from structural
-- steel fixtures to pressure-vessel fixtures needs a fixture change).
INSERT INTO changeover_matrix(from_family, to_family, changeover_min) VALUES
  ('WELD-STRUCT', 'WELD-PV', 90),
  ('WELD-PV', 'WELD-STRUCT', 90),
  ('QC-NDT', 'QC-NDT-STRICT', 45),
  ('QC-NDT-STRICT', 'QC-NDT', 45);

COMMIT;
