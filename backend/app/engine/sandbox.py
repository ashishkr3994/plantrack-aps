"""What-if sandbox: solve against a COPY of the live plan with overrides,
without persisting anything to the live schedule.

A planner supplies overrides — change an order's quantity, due date, or priority,
or exclude an order — plus plan levers (overtime, partial quantity) and solver
settings. We load the real scheduling input, apply everything in memory, run the
CP-SAT engine, and return rich results: real calendar dates per order, the
affected routing operations (which step moved, onto which machine, and when), and
a baseline-vs-scenario comparison. Nothing is written to planned_schedule.

This answers, safely and visually:
  * "How soon can we?"  -> forward mode start/finish dates
  * "When must we start?" -> backward mode start dates
  * "What if we add overtime / cut the qty / expedite?" -> the levers below
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
    partial_qty: int | None = None        # reschedule only part of the order


@dataclass
class SandboxRequest:
    overrides: list[OrderOverride] = field(default_factory=list)
    mode: str = "forward"
    time_budget_s: int = 15
    overtime_hrs_per_day: int = 0          # extra working hours/day (plan lever)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def run_sandbox(db: Session, req: SandboxRequest) -> dict:
    # ---- baseline: the live plan, untouched, default working day ----
    si_base = load_scheduling_input(db)
    base_cal = si_base.calendar
    baseline = cpsat_solve(si_base, max_seconds=req.time_budget_s)

    # ---- scenario: reload fresh, apply overrides + levers ----
    minutes_per_day = 600 + max(0, int(req.overtime_hrs_per_day)) * 60
    si = load_scheduling_input(db, minutes_per_day=minutes_per_day)
    cal = si.calendar
    by_id = {o.order_id: o for o in si.orders}
    overrides = {ov.order_id: ov for ov in req.overrides}

    kept = []
    applied = []   # human-readable record of what the scenario changed
    for o in si.orders:
        ov = overrides.get(o.order_id)
        if ov and ov.exclude:
            applied.append(f"{o.order_id}: excluded")
            continue
        if ov:
            if ov.partial_qty is not None and ov.partial_qty > 0:
                o.qty = ov.partial_qty
                applied.append(f"{o.order_id}: partial qty {ov.partial_qty}")
            elif ov.qty is not None and ov.qty > 0:
                o.qty = ov.qty
                applied.append(f"{o.order_id}: qty -> {ov.qty}")
            if ov.priority in ("HIGH", "MED", "LOW"):
                o.priority = ov.priority
                applied.append(f"{o.order_id}: priority -> {ov.priority}")
            if ov.committed_due_dt:
                try:
                    due = datetime.fromisoformat(ov.committed_due_dt)
                    if due.tzinfo is None:
                        due = due.replace(tzinfo=timezone.utc)
                    o.committed_due_dt = due
                    o.committed_due_min = max(0, cal.working_minutes_between(si.origin, due))
                    applied.append(f"{o.order_id}: due -> {due.date().isoformat()}")
                except ValueError:
                    pass
        kept.append(o)
    si.orders = kept
    if req.overtime_hrs_per_day:
        applied.append(f"overtime: +{req.overtime_hrs_per_day}h/day")

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
            "bottleneck": res.explain.get("bottleneck_machine") if res.explain else None,
        }

    # per-order dates + delta, baseline vs scenario
    base_orders = {o.order_id: o for o in baseline.orders}
    # operation start per order (earliest op start) to report a start date
    def order_start_min(res, oid):
        starts = [op.start_min for op in res.operations if op.order_id == oid]
        return min(starts) if starts else None

    orders_out = []
    for o in scenario.orders:
        b = base_orders.get(o.order_id)
        s_min = order_start_min(scenario, o.order_id)
        # forward: report earliest start + finish. backward: the latest-start read
        # is the same start the solver chose from the due date.
        orders_out.append({
            "order_id": o.order_id,
            "mode": req.mode,
            "start_dt": _iso(cal.to_datetime(s_min)) if s_min is not None else None,
            "finish_dt": _iso(cal.to_datetime(o.completion_min)),
            "due_dt": _iso(cal.to_datetime(o.committed_due_min)),
            "on_time": o.on_time,
            "lateness_min": o.lateness_min,
            "baseline_finish_dt": _iso(base_cal.to_datetime(b.completion_min)) if b else None,
            "baseline_lateness_min": b.lateness_min if b else None,
            "changed": bool(b and b.lateness_min != o.lateness_min),
            "reason": o.bottleneck,
        })

    # affected routing operations: which step, which machine, start/finish, and
    # whether it moved vs baseline
    base_ops = {(op.order_id, op.operation_seq): op for op in baseline.operations}
    ops_out = []
    for op in scenario.operations:
        b = base_ops.get((op.order_id, op.operation_seq))
        moved = bool(b and (b.start_min != op.start_min or b.work_center != op.work_center))
        ops_out.append({
            "order_id": op.order_id,
            "operation_seq": op.operation_seq,
            "work_center": op.work_center,
            "start_dt": _iso(cal.to_datetime(op.start_min)),
            "finish_dt": _iso(cal.to_datetime(op.end_min)),
            "baseline_work_center": b.work_center if b else None,
            "baseline_start_dt": _iso(base_cal.to_datetime(b.start_min)) if b else None,
            "moved": moved,
        })
    ops_out.sort(key=lambda r: (r["order_id"], r["operation_seq"]))

    return {
        "mode": req.mode,
        "question": ("How soon can we finish?" if req.mode == "forward"
                     else "When must we start to hit due dates?"),
        "baseline": summarize(baseline),
        "scenario": summarize(scenario),
        "orders": sorted(orders_out, key=lambda d: d["order_id"]),
        "operations": ops_out,
        "applied_changes": applied,
        "note": "Sandbox only - the live schedule was not modified.",
        "baseline_order_count": len(by_id),
    }
