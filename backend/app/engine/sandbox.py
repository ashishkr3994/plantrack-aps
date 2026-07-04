"""What-if sandbox: solve against a COPY of the live plan with overrides,
without persisting anything to the live schedule.

A planner supplies overrides — change an order's quantity, due date, or priority,
or exclude an order — plus solver settings. We load the real scheduling input,
apply the overrides in memory, run the CP-SAT engine, and return the resulting
metrics and per-order outcomes. Nothing is written to planned_schedule.

This lets planners answer "what if we expedite ORD-x / cut the qty / drop this
order" and compare against the live baseline, safely.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .loader import load_scheduling_input
from .cpsat_engine import solve as cpsat_solve


@dataclass
class OrderOverride:
    order_id: str                  # business id
    qty: int | None = None
    priority: str | None = None
    committed_due_dt: str | None = None   # ISO date
    exclude: bool = False


@dataclass
class SandboxRequest:
    overrides: list[OrderOverride] = field(default_factory=list)
    mode: str = "forward"
    time_budget_s: int = 15


def run_sandbox(db: Session, req: SandboxRequest) -> dict:
    si = load_scheduling_input(db)

    # index live orders by business id, capture a baseline snapshot
    by_id = {o.order_id: o for o in si.orders}
    overrides = {ov.order_id: ov for ov in req.overrides}

    # Run baseline (live input, untouched) for comparison
    baseline = cpsat_solve(si, max_seconds=req.time_budget_s)

    # Apply overrides in memory
    cal = si.calendar
    kept = []
    for o in si.orders:
        ov = overrides.get(o.order_id)
        if ov and ov.exclude:
            continue
        if ov:
            if ov.qty is not None and ov.qty > 0:
                o.qty = ov.qty
            if ov.priority in ("HIGH", "MED", "LOW"):
                o.priority = ov.priority
            if ov.committed_due_dt:
                try:
                    due = datetime.fromisoformat(ov.committed_due_dt)
                    if due.tzinfo is None:
                        due = due.replace(tzinfo=timezone.utc)
                    o.committed_due_dt = due
                    o.committed_due_min = max(0, cal.working_minutes_between(si.origin, due))
                except ValueError:
                    pass
        kept.append(o)
    si.orders = kept

    scenario = cpsat_solve(si, max_seconds=req.time_budget_s)

    def summarize(res):
        return {
            "status": res.status,
            "feasible": res.feasible,
            "makespan": res.makespan,
            "weighted_tardiness": res.weighted_tardiness,
            "orders_total": len(res.orders),
            "orders_on_time": sum(1 for o in res.orders if o.on_time),
            "wall_time_s": res.wall_time_s,
        }

    # per-order delta (completion minute) baseline vs scenario
    base_orders = {o.order_id: o for o in baseline.orders}
    deltas = []
    for o in scenario.orders:
        b = base_orders.get(o.order_id)
        deltas.append({
            "order_id": o.order_id,
            "on_time": o.on_time,
            "lateness_min": o.lateness_min,
            "baseline_lateness_min": b.lateness_min if b else None,
            "changed": bool(b and b.lateness_min != o.lateness_min),
        })

    return {
        "baseline": summarize(baseline),
        "scenario": summarize(scenario),
        "orders": sorted(deltas, key=lambda d: d["order_id"]),
        "note": "Sandbox only — the live schedule was not modified.",
        "baseline_order_count": len(by_id),
    }