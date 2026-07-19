"""Create and list actual (hand-logged) execution events.

Mirrors the prototype's event logging. A 'material_ready' event confirms
material arrival: it stamps material_status.actual_ready_dt and re-evaluates
material risk so the KPI reflects reality immediately. If the confirmed
arrival was genuinely late, it also automatically runs a targeted
single-order recovery -- see create_event for why this matters: showing
"on track" only ever reflects the REAL, persisted, executable schedule,
never a hypothetical "could be fixed" possibility. Writes require planner+.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..deps import require_role, audit
from ..engine.material_risk import evaluate_material_risk
from ..engine.recovery import recover_order, RecoveryOptions

router = APIRouter(prefix="/events", tags=["events"])

VALID_EVENT_TYPES = {
    "material_ready", "start", "pause", "resume",
    "complete", "scrap", "dispatch", "delivered",
}


@router.get("", response_model=list[schemas.EventRead])
def list_events(order_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(models.ActualEvent)
    if order_id is not None:
        q = q.filter_by(order_id=order_id)
    return q.order_by(models.ActualEvent.event_timestamp.desc()).all()


@router.post("", status_code=201)
def create_event(payload: schemas.EventCreate,
                 actor: models.AppUser = Depends(require_role("planner")),
                 db: Session = Depends(get_db)):
    order = db.get(models.OrderHeader, payload.order_id)
    if not order:
        raise HTTPException(422, f"order_id {payload.order_id} does not exist")
    if payload.event_type not in VALID_EVENT_TYPES:
        raise HTTPException(422, f"invalid event_type '{payload.event_type}'")
    if db.query(models.ActualEvent).filter_by(event_id=payload.event_id).first():
        raise HTTPException(409, f"event_id {payload.event_id} already exists")

    data = payload.model_dump()
    whole_wc = data.pop("downtime_whole_wc", False)
    # Encode work-centre-wide scope as a '[WC]' prefix on the reason text, which
    # the solver-loader decodes (avoids a schema migration for one flag).
    if payload.event_type == "pause" and whole_wc:
        reason = data.get("downtime_reason") or "Downtime"
        if not reason.startswith("[WC]"):
            data["downtime_reason"] = f"[WC] {reason}"
    obj = models.ActualEvent(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)

    recovery_outcome = None
    # material_ready confirms arrival -> update material status + re-evaluate risk
    if payload.event_type == "material_ready":
        ms = db.query(models.MaterialStatus).filter_by(order_id=order.id).first()
        if ms:
            ms.actual_ready_dt = payload.event_timestamp
            db.commit()
        evaluate_material_risk(db)
        db.refresh(ms) if ms else None

        # Only bother running a recovery if the confirmed arrival was
        # genuinely late (status == "late" after re-evaluation) -- an
        # on-time confirmation has nothing to recover from. This is
        # deliberately synchronous: this deployment runs single-process
        # (PLANTRACK_SINGLE_PROCESS=1), so there's no real background-task
        # option here anyway, and material confirmations are infrequent
        # enough that a few seconds of added latency for a genuinely useful
        # auto-correction is a fair trade.
        if ms and ms.status == "late":
            try:
                result = recover_order(
                    db, order.order_id,
                    RecoveryOptions(mode="forward", time_budget_s=10),
                    performed_by=actor.username)
            except ValueError:
                result = {"feasible": False}
            if result.get("feasible") and result.get("on_time"):
                recovery_outcome = {
                    "status": "recovered", "on_time": True,
                    "message": f"Material confirmed late; {order.order_id} was "
                               "automatically recovered and is back on schedule.",
                    "new_delivery": result.get("new_delivery"),
                }
                audit(db, actor, "auto_recover", "order", order.order_id,
                      {"trigger": "material_ready", "outcome": "on_time"})
            elif result.get("feasible"):
                recovery_outcome = {
                    "status": "recovered_late", "on_time": False,
                    "message": f"Material confirmed late; {order.order_id} was "
                               "rescheduled but is still behind -- manual action "
                               "(overtime, expedite) may help.",
                    "lateness_min": result.get("lateness_min"),
                }
                audit(db, actor, "auto_recover", "order", order.order_id,
                      {"trigger": "material_ready", "outcome": "still_late"})
            else:
                recovery_outcome = {
                    "status": "infeasible", "on_time": False,
                    "message": f"Material confirmed late; no feasible automatic "
                               f"recovery was found for {order.order_id} -- "
                               "manual intervention is needed.",
                }
                audit(db, actor, "auto_recover", "order", order.order_id,
                      {"trigger": "material_ready", "outcome": "infeasible"})

    audit(db, actor, "log_event", "event", obj.event_id,
          {"type": payload.event_type, "order_id": order.order_id})

    out = schemas.EventRead.model_validate(obj).model_dump()
    out["recovery_outcome"] = recovery_outcome
    return out  
