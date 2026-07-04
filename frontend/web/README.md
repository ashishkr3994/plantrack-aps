# frontend/web — Production UI (React + TypeScript)

The Phase 3 production frontend: a React/TypeScript single-page app that consumes
the FastAPI backend and replaces the prototype's localStorage with live API calls.

## Stack
- **React 18 + TypeScript** (strict)
- **Vite** build/dev server
- **React Router** for screen navigation
- **TanStack Query** for data fetching, caching, loading/error state
- **Recharts** for analytics
- **WebSocket** live updates (auto-reconnecting)

## Screens (ported from the prototype)
Dashboard, Orders, Schedule, Capacity, Materials & BOM, Reschedule, Analytics,
Configuration — see `src/screens/`.

## Key pieces
- `src/api/` — typed client (`client.ts`) + types mirroring backend schemas (`types.ts`).
- `src/hooks/queries.ts` — React Query hooks (data + mutations).
- `src/hooks/useSolve.ts` — the async-solve UX: kick off a solve, poll the job,
  surface progress and the result.
- `src/hooks/useLiveUpdates.ts` — WebSocket connection with reconnect; invalidates
  caches when the server pushes `schedule_updated` / `alert_raised` / `order_changed`.
- `src/components/ui.tsx` — loading, error, empty states, pills, modal.

## Run (dev)
```bash
# 1) start the backend (repo root): docker compose up -d db && cd backend && uvicorn app.main:app --reload
# 2) start the frontend:
cd frontend/web
npm install
npm run dev          # http://localhost:5173 (proxies /api and /ws to :8000)
```

## Build / typecheck
```bash
npm run typecheck    # tsc --noEmit (strict, zero errors)
npm run build        # production bundle in dist/
```

## What's intentionally deferred
- Auth/login (Phase 4) — screens currently assume an authenticated planner.
- Drag-to-reschedule Gantt and the editable master-data forms beyond Orders are
  read-oriented here; they build on the same client and hooks.

db/frontend/web/.env.example


# Copy to .env.local for local overrides.
# In dev, Vite proxies /api and /ws to http://localhost:8000 (see vite.config.ts),
# so these are only needed if the API lives elsewhere.
# VITE_API_BASE=https://api.example.com
# VITE_WS_URL=wss://api.example.com/ws