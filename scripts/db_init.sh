
#!/usr/bin/env bash
# Apply the schema migration and seed data to a target PostgreSQL.
#   PGURL=postgresql://user:pass@host:5432/plantrack ./scripts/db_init.sh
set -euo pipefail
PGURL="${PGURL:-postgresql://plantrack:plantrack@localhost:5432/plantrack}"
ROOT="$(dirname "$0")/.."
echo "Applying schema to $PGURL"
psql "$PGURL" -f "$ROOT/db/migrations/0001_initial_schema.sql"
psql "$PGURL" -f "$ROOT/db/migrations/0002_solve_jobs.sql"
psql "$PGURL" -f "$ROOT/db/migrations/0003_auth_audit_stale.sql"
psql "$PGURL" -f "$ROOT/db/migrations/0004_solver_eligibility_setup.sql"
psql "$PGURL" -f "$ROOT/db/migrations/0005_auth_hardening.sql"
echo "Applying seed to $PGURL"
psql "$PGURL" -f "$ROOT/db/seeds/0001_sample_data.sql"
psql "$PGURL" -f "$ROOT/db/seeds/0002_users.sql"
echo "Done."
