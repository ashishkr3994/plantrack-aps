-- =====================================================================
-- DEMO PRODUCTS — realistic to a plasma-cutting / welding / CNC / powder-
-- coating fabrication shop. Structural-steel family uses R-FAB-STD;
-- pressure-vessel family uses R-FAB-PV (heavier NDT, longer weld).
-- =====================================================================
BEGIN;

INSERT INTO product(product_id, name, family, routing_id)
SELECT 'P-BRK-100', 'Heavy-Duty Mounting Bracket', 'Structural Steel', id FROM routing WHERE route_id='R-FAB-STD';
INSERT INTO product(product_id, name, family, routing_id)
SELECT 'P-FRM-200', 'Machine Base Frame', 'Structural Steel', id FROM routing WHERE route_id='R-FAB-STD';
INSERT INTO product(product_id, name, family, routing_id)
SELECT 'P-PLT-300', 'Structural Gusset Plate Assembly', 'Structural Steel', id FROM routing WHERE route_id='R-FAB-STD';
INSERT INTO product(product_id, name, family, routing_id)
SELECT 'P-CHS-400', 'Welded Chassis Sub-Frame', 'Structural Steel', id FROM routing WHERE route_id='R-FAB-STD';
INSERT INTO product(product_id, name, family, routing_id)
SELECT 'P-VES-500', 'Pressure Vessel Head (ASME)', 'Pressure Vessel', id FROM routing WHERE route_id='R-FAB-PV';
INSERT INTO product(product_id, name, family, routing_id)
SELECT 'P-TNK-600', 'Welded Tank Shell Section', 'Pressure Vessel', id FROM routing WHERE route_id='R-FAB-PV';

-- BOM lines: plate steel, welding consumables, coating, fasteners —
-- realistic to this shop.
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Hot-rolled steel plate, 10mm', 18.5, 'kg', 'Bharat Steel Traders', 4 FROM product WHERE product_id='P-BRK-100';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'MIG welding wire ER70S-6', 0.9, 'kg', 'Weldwell India', 2 FROM product WHERE product_id='P-BRK-100';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Powder coat (RAL 7016)', 0.4, 'kg', 'CoatTech Powders', 3 FROM product WHERE product_id='P-BRK-100';

INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Hot-rolled steel plate, 16mm', 62.0, 'kg', 'Bharat Steel Traders', 4 FROM product WHERE product_id='P-FRM-200';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'MIG welding wire ER70S-6', 2.4, 'kg', 'Weldwell India', 2 FROM product WHERE product_id='P-FRM-200';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Structural steel angle 50x50x6', 8.0, 'pcs', 'Bharat Steel Traders', 5 FROM product WHERE product_id='P-FRM-200';

INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Hot-rolled steel plate, 8mm', 9.2, 'kg', 'Bharat Steel Traders', 3 FROM product WHERE product_id='P-PLT-300';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'MIG welding wire ER70S-6', 0.6, 'kg', 'Weldwell India', 2 FROM product WHERE product_id='P-PLT-300';

INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Hot-rolled steel plate, 12mm', 44.0, 'kg', 'Bharat Steel Traders', 4 FROM product WHERE product_id='P-CHS-400';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'MIG welding wire ER70S-6', 1.8, 'kg', 'Weldwell India', 2 FROM product WHERE product_id='P-CHS-400';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Powder coat (RAL 9005)', 0.9, 'kg', 'CoatTech Powders', 3 FROM product WHERE product_id='P-CHS-400';

-- Pressure-vessel family: heavier plate, certified consumables, longer
-- supplier lead time (drives the "material-bound, overtime can't fix it"
-- scenario for order 9007).
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'ASME SA-516 Gr.70 plate, 20mm', 145.0, 'kg', 'National Alloy & Steel', 12 FROM product WHERE product_id='P-VES-500';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Certified low-hydrogen electrode E7018', 6.5, 'kg', 'Weldwell India', 6 FROM product WHERE product_id='P-VES-500';

INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'ASME SA-516 Gr.70 plate, 16mm', 210.0, 'kg', 'National Alloy & Steel', 12 FROM product WHERE product_id='P-TNK-600';
INSERT INTO bom_line(product_id, material, qty_per_unit, uom, supplier, lead_days)
SELECT id, 'Certified low-hydrogen electrode E7018', 9.0, 'kg', 'Weldwell India', 6 FROM product WHERE product_id='P-TNK-600';

COMMIT;
