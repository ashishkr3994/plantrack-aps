# PlanTrack APS Control Tower

An Advanced Planning & Scheduling (APS) control tower for discrete manufacturing:
finite-capacity, operation-level scheduling with material-availability checks,
multi-signal risk detection, exception-management alerts, and versioned replanning.

This repository is the production codebase. It supersedes the original single-file
HTML prototype (kept under `frontend/` as the reference implementation and demo).

## Layout

| Path | Contents |
|------|----------|
| `backend/`  | FastAPI service — REST API + scheduling-engine orchestration (Phase 1+) |
| `solver/`   | OR-Tools CP-SAT scheduling model, stress test, unit tests |
| `frontend/web/` | React + TypeScript app (Phase 3). `frontend/control-tower.html` kept as reference |
| `db/migrations/` | SQL schema migrations — source of truth for the data model |
| `db/seeds/` | Sample / seed data |
| `docs/adr/` | Architecture Decision Records |
| `scripts/`  | Dev/ops helper scripts |
| `.github/workflows/` | CI pipelines |

## Status by phase

- **Phase 0 — Foundation & de-risking:** ✅ complete
  - Formal PostgreSQL schema (`db/migrations/0001_initial_schema.sql`), validated.
  - Working, verified CP-SAT solver (`solver/`), stress-tested to 1,000 orders.
  - Stack chosen and recorded in `docs/adr/`.
  - Repo structure + CI in place.
- **Phase 1 — Persistence layer:** ✅ core complete
  - PostgreSQL schema + idempotent seed (`db/seeds/0001_sample_data.sql`).
  - FastAPI backend with CRUD for products, orders, BOM, events, routings, and
    dashboard views (`backend/`), verified by integration tests against a real
    Postgres and by a live over-HTTP run.
  - `docker compose up` brings up Postgres (auto-loaded with schema+seed) + API.
  - Remaining: port the scheduling engine to run server-side (bridges into
    Phase 2), and wire the frontend to the API (bridges into Phase 3).
- **Phase 2 — Real optimization engine:** ✅ complete
  - CP-SAT engine (`backend/app/engine/`) integrated into the backend: interval
    variables, no-overlap/cumulative capacity, precedence, parallel groups,
    material-ready earliest-start; priority-weighted-tardiness objective, time-boxed.
  - Async solves via Celery (`POST /schedule/solve` -> poll `/schedule/jobs/{id}`),
    Redis in prod, eager mode in tests.
  - Results persisted to `planned_schedule` + `order_operation`, readable via API.
  - Hard validation: solver is feasible and >= the ported heuristic baseline, and
    respects finite capacity the heuristic violates (8 overloaded WCs -> 0).
- **Phase 3 — Production frontend:** ✅ core complete
  - React + TypeScript app (`frontend/web/`): all eight screens ported, typed API
    client, TanStack Query data layer, Recharts analytics.
  - Async-solve UX (`useSolve`): trigger a solve, live progress, result surfaced.
  - Real-time updates via WebSocket (`useLiveUpdates` + backend `/ws` hub) with
    auto-reconnect; loading/error/empty states and form validation throughout.
  - Type-checks clean (strict) and produces a production build.
- **Phase 4 — Auth, roles, audit, multi-user:** ✅ core complete
  - JWT login, PBKDF2 password hashing; roles viewer<procurement<supervisor<planner<admin.
  - Mutations require planner+, user management & audit trail require admin; reads open.
  - Append-only audit log of creates/updates/deletes/solves/logins.
  - Routing changes flag affected schedules stale (with reason) so planners re-solve.
  - Frontend: login screen, session restore, role-gated write UI, admin screen
    (users + audit). Default seeded users (admin/planner/viewer) — change in prod.
- **Phase 5 — Import, events, material risk, what-if:** ✅ core complete
  - CSV import for orders/products/BOM (`/import/*`) — the ERP stand-in; idempotent,
    per-row error reporting. Hand-logged execution events (`/events`), planner-gated.
  - Proactive time-based material risk: an order is flagged `risk` as its planned
    material-ready date approaches with no confirmed arrival (and `late` once it
    passes), so the Material-at-risk KPI lights up before a late arrival is logged.
  - What-if sandbox (`/sandbox/simulate`): solve scenarios (qty/priority/due/exclude
    overrides) against a copy of the live plan, compare baseline vs scenario — never
    persists. New "What-if sandbox" and "Import data" tabs in the UI.
- **Deviation & alert engine:** ✅ complete
  - Server-side comparison of actuals vs baseline (8 signals ported from the
    prototype): late/silent start, downtime, scrap, material delay, run-rate,
    buffer erosion, capacity overload. Writes deviation_log + role-targeted
    alert_log; runs after each solve and on demand (`/alerts/run-engine`).
  - Role-targeted alerts (procurement/supervisor/planner) with ack/close that
    survive regeneration; Alerts screen with "my role" filter.
  - capacity_load now computed from the schedule (Capacity screen populated).
  - Admins can edit existing users' roles (`PATCH /auth/users/{id}`); last-admin guard.
- **Solver upgrades:** ✅ machine eligibility (alternate work centers, load
  balancing), sequence-dependent setup (setup families + changeover matrix),
  warm-start from the current schedule, and explainability (bottleneck machine,
  per-machine load, per-order late reasons surfaced in the Reschedule screen).
- **Live updates + scheduler + recovery:** ✅ complete
  - WebSocket broadcasts wired (schedule_updated / alert_raised / order_changed) via
    a sync-safe event bus (Redis pub/sub across processes, in-process fallback) — the
    UI now updates live.
  - Celery beat periodic scan runs material-risk + capacity + deviation engines on a
    timer (`PLANTRACK_SCAN_INTERVAL_S`), so time-based alerts fire on their own.
  - Single-order recovery (`/schedule/orders/{id}/recover`): targeted re-solve with
    overtime / partial-qty / mode levers; saves a new version + writes reschedule_log.
  - UI conveniences: KPI drill-downs, CSV template downloads + data export, recovery
    panel with reschedule history.
- **Future:** real ERP/MES connectors (CSV is the current stand-in), drag-to-reschedule
  Gantt, horizon decomposition at high volume, deployment hardening (refresh tokens,
  secrets, monitoring, backups), windowed-overtime in the calendar model.

## Quick start

### Solver
```bash
cd solver
pip install -r requirements.txt
python3 cpsat_scheduler.py        # run the sample schedule
python3 stress_test.py            # scaled-up stress test
pytest -q                         # unit tests
```

### Database schema
```bash
# against any PostgreSQL 14+ instance:
psql -d plantrack -f db/migrations/0001_initial_schema.sql
python3 scripts/validate_schema.py   # CI-friendly validation (embedded PG)
```

### Backend API
```bash
docker compose up -d db          # Postgres, auto-loaded with schema + seed
cd backend && pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://plantrack:plantrack@localhost:5432/plantrack
uvicorn app.main:app --reload    # docs at http://localhost:8000/docs
# trigger an optimised solve (async):
#   curl -XPOST localhost:8000/schedule/solve -H 'Content-Type: application/json' -d '{"time_budget_s":30}'
#   curl localhost:8000/schedule/jobs/<job_id>
# tests (no external DB needed — uses an embedded Postgres):
PYTHONPATH=. pytest app/tests -q
```

### Whole stack with Docker
```bash
docker compose up                # Postgres + API together
```

### Production frontend (React + TS)
```bash
cd frontend/web
npm install
npm run dev      # http://localhost:5173, proxies /api and /ws to the backend on :8000
npm run build    # production bundle; npm run typecheck for strict type checking
```

### Prototype (reference UI)
Open `frontend/control-tower.html` in a browser (kept as reference).

## Decisions
See `docs/adr/` for why PostgreSQL, FastAPI, OR-Tools CP-SAT, and React/TypeScript
were chosen, and for the horizon+decomposition scheduling strategy.
