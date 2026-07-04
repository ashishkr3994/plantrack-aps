-- =====================================================================
--  Seed 0002 — initial users (Phase 4)
--  Default credentials for first login — CHANGE IN PRODUCTION.
--    admin   / admin123     (full access incl. user mgmt + audit)
--    planner / planner123   (create/edit orders, BOM, routings, solve)
--    viewer  / viewer123    (read-only)
-- =====================================================================
BEGIN;
INSERT INTO app_user(username, full_name, role, password_hash) VALUES
  ('admin',   'Administrator',  'admin',   'pbkdf2_sha256$240000$332d0bd954ba609ad94cc3a29547ca67$d15982e1bc773983fe600b030601ef790d518873a79e984e29b9f4fe8d16dfe9'),
  ('planner', 'Plant Planner',  'planner', 'pbkdf2_sha256$240000$b9c2373c2d3acd9439066cfc0fac9b8b$dcfd600539c683bb5d31d021d2c3eb8a12438be7c792cb103fdcbd30e0252f0f'),
  ('viewer',  'Read Only',      'viewer',  'pbkdf2_sha256$240000$4e2b892dd08897c9b750d9ba84916218$4490faac843aa2bd5a096a10958fb2bda9f242a648de12b82425db4728fb278d')
ON CONFLICT (username) DO NOTHING;
COMMIT;
