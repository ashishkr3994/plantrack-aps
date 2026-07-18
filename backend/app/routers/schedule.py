"""Scheduling endpoints: kick off an async CP-SAT solve, poll its status,
and read the resulting schedule.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..jobs.tasks import solve_schedule
from ..deps import require_role, audit
from ..engine.recovery import recover_order, RecoveryOptions
from ..events_bus import publish

router = APIRouter(prefix="/schedule", tags=["schedule"])


class SolveRequest(BaseModel):
    mode: str = "forward"
    time_budget_s: int = 30
    order_ids: list[str] | None = None     # business ids; null = all
    leveling: str = "off"                  # 'off' | 'soft' | 'strict'


class SolveJobRead(BaseModel):
    job_id: str
    status: str
    result: dict | None = None
    error: str | None = None


@router.post("/solve", response_model=SolveJobRead, status_code=202)
def kick_off_solve(req: SolveRequest, actor: models.AppUser = Depends(require_role("planner")), db: Session = Depends(get_db)):
    """Queue an async solve. Returns immediately with a job id to poll.
    Never blocks on the solver."""
    job_id = str(uuid.uuid4())
    leveling = req.leveling if req.leveling in ("off", "soft", "strict") else "off"
    job = models.SolveJob(
        job_id=job_id, status="queued", mode=req.mode,
        time_budget_s=req.time_budget_s, order_ids=req.order_ids,
        created_at=datetime.now(timezone.utc))
    db.add(job)
    db.commit()
    # dispatch to Celery (eager in tests/dev; real worker in prod)
    solve_schedule.delay(job_id, req.mode, req.time_budget_s, req.order_ids, leveling)
    audit(db, actor, "solve", "schedule", job_id, {"mode": req.mode, "budget_s": req.time_budget_s, "leveling": leveling})
    return SolveJobRead(job_id=job_id, status=job.status)


@router.get("/jobs/{job_id}", response_model=SolveJobRead)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(models.SolveJob).filter_by(job_id=job_id).first()
    if not job:
        raise HTTPException(404, "job not found")
    return SolveJobRead(job_id=job.job_id, status=job.status,
                        result=job.result, error=job.error)


@router.get("/orders/{order_id}")
def get_order_schedule(order_id: str, db: Session = Depends(get_db)):
    """Return the current schedule + operations for an order (by business id)."""
    o = db.query(models.OrderHeader).filter_by(order_id=order_id).first()
    if not o:
        raise HTTPException(404, "order not found")
    sched = db.execute(text(
        "SELECT * FROM planned_schedule WHERE order_id=:o AND is_current"),
        {"o": o.id}).mappings().first()
    ops = db.execute(text(
        "SELECT operation_seq, work_center, parallel_group, predecessor_operation_seq, "
        "planned_start, planned_end, duration_mins FROM order_operation "
        "WHERE order_id=:o ORDER BY operation_seq"), {"o": o.id}).mappings().all()
    return {"order_id": order_id,
            "schedule": dict(sched) if sched else None,
            "operations": [dict(r) for r in ops]}


@router.get("/gantt")
def get_gantt_data(db: Session = Depends(get_db)):
    """All CURRENT operations across every order, for the shop-wide timeline
    view: machines on one axis, time on the other. Read-only; changes nothing.
    Also returns logged downtime windows so outages render alongside real work.
    """
    ops = db.execute(text("""
        SELECT oo.work_center, oo.operation_seq, oo.planned_start, oo.planned_end,
               oo.parallel_group, o.order_id, o.priority, o.customer,
               (
                 COALESCE(ro.setup_min, 0) + COALESCE(ro.run_per_unit_min, 0) * o.order_qty
                 + COALESCE(ro.queue_min, 0) + COALESCE(ro.move_min, 0)
               ) / 60.0 AS busy_hrs
        FROM order_operation oo
        JOIN order_header o ON o.id = oo.order_id
        JOIN planned_schedule ps ON ps.id = oo.schedule_id AND ps.is_current
        LEFT JOIN product p ON p.id = o.product_id
        LEFT JOIN routing_operation ro ON ro.routing_id = p.routing_id
            AND ro.operation_seq = oo.operation_seq
        WHERE oo.planned_start IS NOT NULL AND oo.planned_end IS NOT NULL
        ORDER BY oo.work_center, oo.planned_start
    """)).mappings().all()

    downtime = db.execute(text("""
        SELECT ae.event_timestamp, ae.downtime_mins, ae.downtime_reason,
               o.order_id, oo.work_center
        FROM actual_event ae
        LEFT JOIN order_header o ON o.id = ae.order_id
        LEFT JOIN order_operation oo ON oo.order_id = ae.order_id
            AND oo.operation_seq = ae.operation_seq
            AND oo.schedule_id = (
                SELECT ps2.id FROM planned_schedule ps2
                WHERE ps2.order_id = ae.order_id AND ps2.is_current
                LIMIT 1
            )
        WHERE ae.event_type = 'pause' AND ae.downtime_mins > 0
        ORDER BY ae.event_timestamp
    """)).mappings().all()

    # Work-centre-wide scope is tagged '[WC]' on the reason (see events.py), but
    # that tag ONLY affects how the SOLVER enforces it (whole machine blocked vs
    # just this order's operation blocked) -- it does NOT determine whether we
    # can place it on the timeline. We already resolve the affected operation's
    # real work centre via the join above for BOTH scopes, so both are shown:
    # an order-scoped pause still visibly marks the outage on that machine's
    # row, it's just labelled as affecting one order rather than the whole shop.
    dt_out = []
    for d in downtime:
        reason = d["downtime_reason"] or ""
        whole_wc = reason.startswith("[WC]")
        dt_out.append({
            "work_center": d["work_center"],
            "whole_wc": whole_wc,
            "order_id": d["order_id"],
            "start": d["event_timestamp"].isoformat(),
            "duration_mins": d["downtime_mins"],
            "reason": reason,
        })

    return {
        "operations": [{
            "work_center": r["work_center"],
            "operation_seq": r["operation_seq"],
            "start": r["planned_start"].isoformat(),
            "end": r["planned_end"].isoformat(),
            "parallel_group": r["parallel_group"],
            "order_id": r["order_id"],
            "priority": r["priority"],
            "customer": r["customer"],
            # true machine-busy time (setup+run+queue+move), independent of
            # calendar placement -- an operation spanning a shift boundary
            # will show a longer start-to-end span than it was actually busy
            # for; this field is what should be trusted as "how long," not
            # (end - start).
            "busy_hrs": round(float(r["busy_hrs"]), 2) if r["busy_hrs"] is not None else None,
        } for r in ops],
        "downtime": dt_out,
    }


class RecoverRequest(BaseModel):
    overtime: bool = False
    overtime_hrs: int = 4
    overtime_from: str | None = None
    overtime_to: str | None = None
    partial_qty: int | None = None
    mode: str = "forward"
    time_budget_s: int = 15


@router.post("/orders/{order_id}/recover")
def recover(order_id: str, body: RecoverRequest,
            actor: models.AppUser = Depends(require_role("planner")),
            db: Session = Depends(get_db)):
    """Targeted single-order recovery - re-solve just this order with recovery
    levers (overtime/partial qty/mode), persist a new version, log it."""
    try:
        opts = RecoveryOptions(
            overtime=body.overtime, overtime_hrs=body.overtime_hrs,
            overtime_from=body.overtime_from, overtime_to=body.overtime_to,
            partial_qty=body.partial_qty, mode=body.mode,
            time_budget_s=min(body.time_budget_s, 60))
        result = recover_order(db, order_id, opts, performed_by=actor.username)
    except ValueError as e:
        raise HTTPException(404, str(e))
    audit(db, actor, "recover", "order", order_id, result.get("options"))
    if result.get("feasible"):
        publish("schedule_updated", {"order_id": order_id, "recovery": True})
    return result


@router.post("/orders/{order_id}/recommend")
def recommend(order_id: str, time_budget_s: int = 8,
             _: models.AppUser = Depends(require_role("planner")),
             db: Session = Depends(get_db)):
    """Read-only: try a small set of overtime levels and suggest the smallest
    one that clears this order's lateness (or the best achievable). Nothing is
    persisted - this is a preview to inform a planner's recovery decision."""
    from ..engine.recovery import recommend_recovery
    try:
        return recommend_recovery(db, order_id, time_budget_s=min(time_budget_s, 20))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/orders/{order_id}/reschedule-log")
def reschedule_log(order_id: str, db: Session = Depends(get_db)):
    o = db.query(models.OrderHeader).filter_by(order_id=order_id).first()
    if not o:
        raise HTTPException(404, "order not found")
    rows = (db.query(models.RescheduleLog)
              .filter_by(order_id=o.id)
              .order_by(models.RescheduleLog.version.desc()).all())
    return [{
        "version": r.version, "options": r.options,
        "baseline_delivery": r.baseline_delivery.isoformat() if r.baseline_delivery else None,
        "new_delivery": r.new_delivery.isoformat() if r.new_delivery else None,
        "performed_by": r.performed_by,
        "performed_at": r.performed_at.isoformat() if r.performed_at else None,
    } for r in rows]
