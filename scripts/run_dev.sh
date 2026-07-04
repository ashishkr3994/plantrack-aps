
#!/usr/bin/env bash
# Start the backend against a local PostgreSQL.
# Prereqs: a running Postgres reachable via $DATABASE_URL (or the default below),
# with the schema + seed applied (see db/). Then:
#   ./scripts/run_dev.sh
set -euo pipefail

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://plantrack:plantrack@localhost:5432/plantrack}"
echo "Using DATABASE_URL=$DATABASE_URL"

cd "$(dirname "$0")/../backend"
pip install -r requirements.txt
exec uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
