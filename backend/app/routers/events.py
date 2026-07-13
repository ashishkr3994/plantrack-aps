"""Create and list actual (hand-logged) execution events.

Mirrors the prototype's event logging. A 'material_ready' event confirms
material arrival: it stamps material_status.actual_ready_dt and re-evaluates
material risk so the KPI reflects reality immediately. Writes require planner+.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..deps import require_role, audit
from ..engine.material_risk import evaluate_material_risk

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


@router.post("", response_model=schemas.EventRead, status_code=201)
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

    # material_ready confirms arrival -> update material status + re-evaluate risk
    if payload.event_type == "material_ready":
        ms = db.query(models.MaterialStatus).filter_by(order_id=order.id).first()
        if ms:
            ms.actual_ready_dt = payload.event_timestamp
            db.commit()
        evaluate_material_risk(db)

    audit(db, actor, "log_event", "event", obj.event_id,
          {"type": payload.event_type, "order_id": order.order_id})
    return obj
