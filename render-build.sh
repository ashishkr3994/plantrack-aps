
#!/usr/bin/env bash
# Render build: backend deps + frontend build (served by the backend).
set -euo pipefail

echo "[build] installing backend dependencies…"
pip install --no-cache-dir -r backend/requirements.txt

echo "[build] building frontend…"
cd frontend/web
npm ci
# same-origin API base: the backend serves the UI, so API lives at root ("")
VITE_API_BASE="" npm run build
cd ../..

echo "[build] done — frontend in frontend/web/dist, served via PLANTRACK_STATIC_DIR"
