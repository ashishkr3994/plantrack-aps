

-- =====================================================================
-- DEMO PRODUCTS v2 -- cutting & welding machine manufacturer.
-- Each new product REUSES the exact routing and BOM lead_days of the
-- product it replaces, so every calibrated story order in 0004_orders.sql
-- keeps behaving identically -- only names/materials changed, not timing.
--   P1 (was P-BRK-100, R-FAB-STD)
--   P2 (was P-PLT-300, R-FAB-STD)
--   P3 (was P-CHS-400, R-FAB-STD)
--   P4 (was P-FRM-200, R-FAB-STD)
--   P5 (was P-VES-500, R-FAB-PV) -- keeps the long 12-day lead the
--        material-story orders (1009/1010/1011) depend on
--   P6 (was P-TNK-600, R-FAB-PV)
-- =====================================================================
BEGIN;

INSERT INTO product(product_id, name, family, routing_id)
SELECT 'P1', 'KALI 100 Cutting Machine', 'Cutting Machine', id FROM routing WHERE route_id='R-FAB-STD';
INSERT INTO product(product_id, name, family, routing_id)
SELECT 'P2', 'CNC Plasma-OxyFuel Pipe Profile Cutting Machine', 'Cutting Machine', id FROM routing WHERE route_id='R-FAB-STD';
INSERT INTO product(product_id, name, family, routing_id)
SELECT 'P3', 'Pipe Profile Cutting Machine With Auto Bevel', 'Cutting Machine', id FROM routing WHERE route_id='R-FAB-STD';
INSERT INTO product(product_id, name, family, routing_id)
SELECT 'P4', 'CNC Fiber Laser Metal Cutting Machine', 'Cutting Machine', id FROM routing WHERE route_id='R-FAB-STD';
INSERT INTO product(product_id, name, family, routing_id)
SELECT 'P5', 'ICP 600 Welding Machine', 'Welding Machine', id FROM routing WHERE route_id='R-FAB-PV';
INSERT INTO product(product_id, name, family, routing_id)
SELECT 'P6', 'Inverter Based Synergic MIG/MAG (CO2) Welding Machine', 'Welding Machine', id FROM routing WHERE route_id='R-FAB-PV';

-- BOM lines: machine-appropriate components, same lead_days as the
-- product each one replaces (preserves every calibrated story exactly).

-- P1 (was P-BRK-100: leads 4d, 2d, 3d)
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'CNC-cut mild steel base frame (structural)', 18.5, 'kg', 'Bharat Steel Traders', 4 FROM product WHERE product_id='P1';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'MIG welding consumables (wire/electrodes)', 0.9, 'kg', 'Weldwell India', 2 FROM product WHERE product_id='P1';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Powder-coated enclosure panels', 0.4, 'kg', 'CoatTech Powders', 3 FROM product WHERE product_id='P1';

-- P2 (was P-PLT-300: leads 3d, 2d)
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'CNC servo motor & drive assembly', 9.2, 'kg', 'Bharat Steel Traders', 3 FROM product WHERE product_id='P2';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Plasma/oxy-fuel torch consumables', 0.6, 'kg', 'Weldwell India', 2 FROM product WHERE product_id='P2';

-- P3 (was P-CHS-400: leads 4d, 2d, 3d)
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Pipe rotation chuck & clamping assembly', 44.0, 'kg', 'Bharat Steel Traders', 4 FROM product WHERE product_id='P3';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Auto-bevel torch head welding consumables', 1.8, 'kg', 'Weldwell India', 2 FROM product WHERE product_id='P3';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Auto-bevel actuator housing (powder-coated)', 0.9, 'kg', 'CoatTech Powders', 3 FROM product WHERE product_id='P3';

-- P4 (was P-FRM-200: leads 4d, 2d, 5d)
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Precision-cut steel gantry structure', 62.0, 'kg', 'Bharat Steel Traders', 4 FROM product WHERE product_id='P4';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Welding consumables (structural joints)', 2.4, 'kg', 'Weldwell India', 2 FROM product WHERE product_id='P4';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Linear guide rails & structural angle sections', 8.0, 'pcs', 'Bharat Steel Traders', 5 FROM product WHERE product_id='P4';

-- P5 (was P-VES-500: leads 12d, 6d) -- keeps the long material lead the
-- material-status stories (1009/1010/1011) are calibrated against.
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Inverter power module & transformer (imported)', 145.0, 'kg', 'National Alloy & Steel', 12 FROM product WHERE product_id='P5';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Certified output cable & electrode holder assembly', 6.5, 'kg', 'Weldwell India', 6 FROM product WHERE product_id='P5';

-- P6 (was P-TNK-600: leads 12d, 9d)
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Synergic control PCB & wire-feed motor (imported)', 210.0, 'kg', 'National Alloy & Steel', 12 FROM product WHERE product_id='P6';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'MIG torch & consumables (contact tips/nozzles)', 9.0, 'kg', 'Weldwell India', 9 FROM product WHERE product_id='P6';

COMMIT;


