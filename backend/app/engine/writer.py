"""Persist a ScheduleResult into planned_schedule + order_operation, converting
working-minute positions back to wall-clock datetimes via the calendar.

For each order we derive the five milestones the product tracks:
  material_ready -> prod_start -> prod_end -> pack -> dispatch -> delivery
using the order's lead times where available (packing/transport/buffer), else
sensible defaults. Each solve produces a new schedule version; the latest is
flagged is_current.
"""
from __future__ import annotations
from datetime import timedelta

from sqlalchemy.orm import Session
from sqlalchemy import text

from .. import models
from .loader import SchedulingInput
from .cpsat_engine import ScheduleResult
from .capacity import compute_capacity_load
from .deviation import run_deviation_engine
from .loader import PACK_DAYS, DISPATCH_DAYS, TRANSPORT_DAYS


def _next_version(db: Session, order_pk: int) -> int:
    row = db.execute(text(
        "SELECT COALESCE(MAX(baseline_version),0)+1 FROM planned_schedule WHERE order_id=:o"),
        {"o": order_pk}).scalar()
    return int(row or 1)


def persist(db: Session, si: SchedulingInput, result: ScheduleResult,
            mode: str = "forward") -> dict:
    cal = si.calendar
    # group scheduled ops by order
    ops_by_order: dict[int, list] = {}
    for op in result.operations:
        ops_by_order.setdefault(op.order_pk, []).append(op)

    written = 0
    for o in si.orders:
        ops = sorted(ops_by_order.get(o.pk, []), key=lambda x: x.operation_seq)
        if not ops:
            continue
        prod_start_min = min(x.start_min for x in ops)
        prod_end_min = max(x.end_min for x in ops)
        prod_start = cal.to_datetime(prod_start_min)
        prod_end = cal.to_datetime(prod_end_min)
        material_ready = cal.to_datetime(o.material_ready_min)
        # downstream milestones off prod_end. Total delivery lead is per-family
        # (o.delivery_lead_days), matching the loader's production due target so
        # solver and reporting agree on on-time. Pack/dispatch are shown as
        # intermediate points within that lead; delivery uses the full lead.
        lead = int(getattr(o, "delivery_lead_days", PACK_DAYS + DISPATCH_DAYS + TRANSPORT_DAYS))
        pack = prod_end + timedelta(days=min(PACK_DAYS, lead))
        dispatch = pack + timedelta(days=min(DISPATCH_DAYS, max(0, lead - PACK_DAYS)))
        delivery = prod_end + timedelta(days=lead)
        buffer_hrs = round((o.committed_due_dt - delivery).total_seconds() / 3600, 2)

        version = _next_version(db, o.pk)
        # demote previous current
        db.execute(text(
            "UPDATE planned_schedule SET is_current=FALSE WHERE order_id=:o AND is_current"),
            {"o": o.pk})
        sched = models.PlannedSchedule(
            schedule_id=f"SCH-{o.order_id}-v{version}", order_id=o.pk,
            baseline_version=version, sched_mode=mode,
            planned_material_ready_dt=material_ready,
            planned_prod_start_dt=prod_start, planned_prod_end_dt=prod_end,
            planned_pack_dt=pack, planned_dispatch_dt=dispatch,
            planned_delivery_dt=delivery,
            prod_duration_mins=prod_end_min - prod_start_min,
            original_buffer_hrs=buffer_hrs, buffer_hrs=buffer_hrs,
            # A successfully-scheduled order always has a valid plan, so it is
            # 'feasible'. Whether it is LATE is a separate dimension captured by
            # buffer_hrs (negative = late) and surfaced as "Late" in the UI.
            # 'infeasible' is reserved for orders the solver genuinely cannot
            # schedule at all (which do not reach this writer path).
            schedule_status="feasible",
            is_current=True, is_stale=False, stale_reason=None)
        db.add(sched)
        db.flush()  # get sched.id

        # replace this order's operations for the new version
        db.execute(text("DELETE FROM order_operation WHERE order_id=:o"), {"o": o.pk})
        # map seq -> routing op (for accurate time components)
        op_def = {op.seq: op for op in o.ops}
        for x in ops:
            d = op_def.get(x.operation_seq)
            db.add(models.OrderOperation(
                order_operation_id=f"{o.order_id}-OP{x.operation_seq}",
                order_id=o.pk, schedule_id=sched.id, operation_seq=x.operation_seq,
                work_center=x.work_center, chosen_work_center=x.work_center,
                planned_qty=o.qty,
                setup_time_min=(d.setup if d else 0),
                run_time_per_unit_min=(d.run_per_unit if d else 0),
                queue_time_min=(d.queue if d else 0),
                move_time_min=(d.move if d else 0),
                predecessor_operation_seq=x.predecessor, parallel_group=x.parallel_group,
                planned_start=cal.to_datetime(x.start_min),
                planned_end=cal.to_datetime(x.end_min),
                duration_mins=x.duration_min, version=version))
        written += 1
    db.commit()
    # refresh derived analytics off the new schedule
    compute_capacity_load(db)
    run_deviation_engine(db)
    return {"orders_scheduled": written}
