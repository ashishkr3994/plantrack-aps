"""Single-order recovery — a targeted reschedule of ONE order, not a full re-solve.

Ported from the prototype's rescheduleOrder. A planner picks an order in trouble
and applies recovery levers:
  * overtime: add extra working minutes per day (optionally only within a date
    window), giving the order more capacity to catch up
  * partial qty: reschedule a reduced quantity (e.g. split the order, ship part)
  * mode: forward (earliest finish) or backward (from due date)

We re-solve just that order against the current shop state, persist a new
schedule version (the writer marks it is_current and supersedes the prior), and
write a reschedule_log row capturing the options and the baseline vs new delivery
so the recovery is auditable. Returns a before/after summary.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import text

from .loader import load_scheduling_input
from .cpsat_engine import solve
from .writer import persist
from .. import models


@dataclass
class RecoveryOptions:
    overtime: bool = False
    overtime_hrs: int = 4
    overtime_from: str | None = None   # ISO date
    overtime_to: str | None = None     # ISO date
    partial_qty: int | None = None
    mode: str = "forward"
    time_budget_s: int = 15


def _current_delivery(db: Session, order_pk: int):
    row = db.execute(text(
        "SELECT planned_delivery_dt FROM planned_schedule "
        "WHERE order_id=:o AND is_current"), {"o": order_pk}).first()
    return row[0] if row else None


def recover_order(db: Session, order_id: str, opts: RecoveryOptions,
                  performed_by: str | None = None) -> dict:
    order = db.query(models.OrderHeader).filter_by(order_id=order_id).first()
    if not order:
        raise ValueError(f"order {order_id} not found")

    baseline_delivery = _current_delivery(db, order.id)

    # Apply overtime as extra minutes/day. A windowed overtime can't be expressed
    # in the flat working-minute model without calendar surgery, so we apply the
    # uplift globally for this targeted solve and record the requested window in
    # the log (transparent about the approximation — see ADR).
    minutes_per_day = 960
    if opts.overtime:
        minutes_per_day += max(0, int(opts.overtime_hrs)) * 60

    # Partial qty: temporarily reschedule a reduced quantity for this order.
    original_qty = order.order_qty
    if opts.partial_qty and opts.partial_qty > 0:
        order.order_qty = opts.partial_qty
        db.flush()

    try:
        si = load_scheduling_input(
            db, minutes_per_day=minutes_per_day, order_ids=[order_id])
        result = solve(si, max_seconds=opts.time_budget_s)
        if not result.feasible:
            return {"feasible": False, "status": result.status,
                    "message": "No feasible recovery found with these options."}
        persist(db, si, result, mode=opts.mode)
    finally:
        # restore the stored qty (the recovery models a scenario, not a qty edit)
        if opts.partial_qty and opts.partial_qty > 0:
            order.order_qty = original_qty
            db.flush()

    new_delivery = _current_delivery(db, order.id)
    new_version = db.execute(text(
        "SELECT MAX(baseline_version) FROM planned_schedule WHERE order_id=:o"),
        {"o": order.id}).scalar() or 1

    # log the reschedule (idempotent on order+version)
    options_json = {
        "overtime": opts.overtime, "overtime_hrs": opts.overtime_hrs,
        "overtime_from": opts.overtime_from, "overtime_to": opts.overtime_to,
        "partial_qty": opts.partial_qty, "mode": opts.mode,
    }
    exists = db.query(models.RescheduleLog).filter_by(
        order_id=order.id, version=new_version).first()
    if not exists:
        db.add(models.RescheduleLog(
            order_id=order.id, version=new_version, options=options_json,
            baseline_delivery=baseline_delivery, new_delivery=new_delivery,
            performed_by=performed_by, performed_at=datetime.now(timezone.utc)))
    # bump replan count
    if hasattr(order, "replan_count"):
        order.replan_count = (order.replan_count or 0) + 1
    db.commit()

    sched_order = next((o for o in result.orders if o.order_id == order_id), None)
    return {
        "feasible": True,
        "order_id": order_id,
        "version": new_version,
        "baseline_delivery": baseline_delivery.isoformat() if baseline_delivery else None,
        "new_delivery": new_delivery.isoformat() if new_delivery else None,
        "on_time": sched_order.on_time if sched_order else None,
        "lateness_min": sched_order.lateness_min if sched_order else None,
        "bottleneck": sched_order.bottleneck if sched_order else None,
        "options": options_json,
    }
