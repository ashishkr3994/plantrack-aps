#!/usr/bin/env bash
set -euo pipefail

echo "[build] installing backend dependencies..."
pip install --no-cache-dir -r backend/requirements.txt

echo "[build] building frontend..."
cd frontend/web
npm ci
VITE_API_BASE="" npm run build
cd ../..

echo "[build] done"
