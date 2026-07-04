# 14. Live updates wiring, periodic scheduler, single-order recovery, UI conveniences

**Status:** Accepted

## Context
The WebSocket hub existed but nothing published to it (so "Live" was inert). The
deviation/material-risk engines only ran on solves/events/on-demand, so time-based
signals didn't surface on their own. Several prototype conveniences were unported:
KPI drill-downs, CSV template downloads / data export, and single-order recovery.

## Decisions
- **Event bus (`events_bus.py`) + live wiring:** a sync-safe `publish()` callable
  from request handlers and the Celery worker. With Redis configured it uses
  pub/sub (works across the worker and multiple web workers); otherwise it relays
  to the in-process async hub. Broadcasts wired: `schedule_updated` (after a
  feasible solve and after recovery), `alert_raised` (when the deviation engine
  raises alerts), `order_changed` (order create/update/delete). The frontend hook
  already invalidates the right caches on each event — so the UI now updates live.
- **Periodic scheduler:** a Celery beat task `periodic_deviation_scan` runs
  material-status + risk + capacity + deviation engines every
  `PLANTRACK_SCAN_INTERVAL_S` (default 300s), so silent-start-miss and
  approaching-material-ready alerts fire on their own. Runs under `celery beat`;
  in eager/test mode it's directly callable.
- **Single-order recovery (`engine/recovery.py`, `/schedule/orders/{id}/recover`):**
  a targeted re-solve of ONE order with recovery levers — overtime (extra
  minutes/day), partial quantity, and mode — that persists a new schedule version
  and writes a `reschedule_log` row (baseline vs new delivery, options, who/when).
  This replaces "reschedule = full re-solve" with the prototype's recovery flow.
  Partial-qty models a scenario; the stored order quantity is restored afterwards.
- **UI conveniences:** clickable KPI drill-downs (orders / open alerts / capacity
  conflicts / material-at-risk) on the dashboard; CSV template downloads and
  current-data export on the Import screen; a recovery panel + reschedule history
  on the Reschedule screen.

## Consequences
- Multi-worker live updates require Redis (the in-process path can't cross the
  worker boundary) — documented; single-process dev/test works without it.
- Windowed overtime is approximated by a global per-day uplift for the targeted
  solve; the requested window is recorded in the log (the flat working-minute
  model can't place a date-bounded uplift without calendar surgery — future work).

