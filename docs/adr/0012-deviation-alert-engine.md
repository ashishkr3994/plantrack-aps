# 12. Server-side deviation & alert engine + capacity load

**Status:** Accepted

## Context
The prototype actively compared actuals against the baseline and raised
role-targeted alerts (computeOrderStatus + generateAlerts). The production system
had the schema (alert_log, deviation_log, capacity_load) but no logic writing to
it — the "control tower" monitoring capability was scaffolding only. Two of the
five RBAC roles (procurement, supervisor) had no behavior. Admins could create
users but not change an existing user's role.

## Decisions
- **Deviation engine (`engine/deviation.py`):** a faithful port of the prototype's
  8 signals — late start, silent start miss, downtime, scrap rework, material
  delay, run-rate shortfall, buffer erosion, capacity overload — producing a
  forecast slip, an order health classification (on/risk/delay/crit) against the
  alert thresholds, and writing `deviation_log`.
- **Role-targeted alerts:** alerts carry an owner and are filterable by the
  caller's role (`/alerts?mine=true`): material -> procurement, silent-miss &
  delivery-breach -> supervisor, buffer & capacity -> planner. This gives the
  procurement and supervisor roles real meaning. Ack/close status is preserved
  across regenerations via the dedup key.
- **Capacity load (`engine/capacity.py`):** computes per-work-center daily load
  from scheduled operations, flags overloaded cells, and populates `capacity_load`
  — feeding both the deviation engine's capacity signal and the Capacity screen
  (previously empty).
- **When it runs:** automatically after every solve (in the writer), and on demand
  via `POST /alerts/run-engine`. In production it should also run on a schedule so
  time-based signals (silent miss) advance with the clock.
- **User role editing:** `PATCH /auth/users/{id}` (admin only) to change role,
  active status, name, or password, with a guard preventing removal of the last
  active admin. The Admin screen now edits roles inline.

## Consequences
- The system now earns the "control tower" name: it watches execution against the
  baseline and surfaces problems by owner.
- Alerts are regenerated wholesale each run (simple, correct); a high-volume
  deployment may want incremental updates and a scheduled job (e.g. Celery beat).
- No new migration: alert_log, deviation_log, capacity_load already existed.

