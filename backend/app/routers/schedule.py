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
