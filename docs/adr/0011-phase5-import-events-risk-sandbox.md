# 11. Phase 5 — CSV import, hand-logged events, proactive material risk, what-if sandbox

**Status:** Accepted

## Context
The product needs data in (without a live ERP yet), a way to record what actually
happens on the floor, earlier warning on material problems, and a safe place to try
changes before committing them.

## Decisions
- **CSV import (`/import/{products,bom,orders}`):** the data feed for now, standing in
  for an ERP connector. Raw CSV in, per-row result out (imported / skipped / errors).
  Idempotent on business keys, so re-importing the same file is safe. After an
  orders/BOM import, material status is re-initialised and risk re-evaluated.
- **Hand-logged events (`/events`):** the prototype's event flow, server-side and
  role-guarded. A `material_ready` event stamps the actual arrival and re-evaluates
  risk immediately, so the picture stays current as the floor reports in.
- **Time-based material risk (`engine/material_risk.py`):** proactive flagging — an
  order is `risk` when its planned material-ready date falls within the
  `mat_risk_window_days` window with no confirmed arrival, and `late` once that date
  passes unconfirmed. The Material-at-risk KPI therefore lights up *before* a late
  arrival is recorded, not only after. Runs on material_ready events and on demand
  (`/materials/evaluate-risk`); intended to run on a schedule in production.
- **What-if sandbox (`engine/sandbox.py`, `/sandbox/simulate`):** runs the CP-SAT
  engine against an in-memory COPY of the live scheduling input with planner overrides
  (change qty / priority / due date, or exclude an order). Returns baseline-vs-scenario
  metrics and per-order deltas. **Never writes to the live schedule tables** — verified
  by test and end-to-end (live schedule version unchanged after a simulation).

## Consequences
- No new DB migration: material risk reuses the existing `material_status` table and
  the `mat_risk_window_days` threshold; import and sandbox are application-layer.
- The frontend gains two tabs — Import data and What-if sandbox — plus a material-risk
  panel on the Materials screen. Both new tabs are planner-gated.
- A real ERP/MES connector would replace CSV import behind the same internal flow.

