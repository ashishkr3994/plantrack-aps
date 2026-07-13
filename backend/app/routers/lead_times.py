"""Per-family lead-time master: list and edit the packing/transport/buffer (and
inbound/QA) day offsets that drive the delivery lead used by the scheduler.

The delivery lead the solver uses per order = packing_days + transport_days +
buffer_days for that product's family. Editing these here changes how far ahead
of the committed date production must finish, per family.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import require_role, audit

router = APIRouter(prefix="/lead-times", tags=["lead-times"])


class LeadTimeRow(BaseModel):
    product_family: str
    inbound_days: float = 0
    qa_days: float = 0
    packing_days: float = 0
    transport_days: float = 0
    buffer_days: float = 0


@router.get("")
def list_lead_times(db: Session = Depends(get_db)):
    """All lead-time rows, plus the derived delivery lead each one produces."""
    rows = db.query(models.LeadTimeMaster).order_by(models.LeadTimeMaster.product_family).all()
    out = []
    for lt in rows:
        pack = float(lt.packing_days or 0)
        trans = float(lt.transport_days or 0)
        buf = float(lt.buffer_days or 0)
        out.append({
            "product_family": lt.product_family,
            "inbound_days": float(lt.inbound_days or 0),
            "qa_days": float(lt.qa_days or 0),
            "packing_days": pack,
            "transport_days": trans,
            "buffer_days": buf,
            # what the scheduler actually uses as the post-production delivery lead
            "delivery_lead_days": pack + trans + buf,
        })
    return out


@router.put("/{product_family}")
def upsert_lead_time(product_family: str, body: LeadTimeRow,
                     actor: models.AppUser = Depends(require_role("planner")),
                     db: Session = Depends(get_db)):
    """Create or update a family's lead times. Re-solve to apply to schedules."""
    for v in (body.inbound_days, body.qa_days, body.packing_days,
              body.transport_days, body.buffer_days):
        if v < 0:
            raise HTTPException(422, "lead-time days cannot be negative")
    lt = db.query(models.LeadTimeMaster).filter_by(product_family=product_family).first()
    if lt is None:
        lt = models.LeadTimeMaster(product_family=product_family)
        db.add(lt)
    lt.inbound_days = body.inbound_days
    lt.qa_days = body.qa_days
    lt.packing_days = body.packing_days
    lt.transport_days = body.transport_days
    lt.buffer_days = body.buffer_days
    db.commit()
    audit(db, actor, "update", "lead_time_master", product_family, body.model_dump())
    return {"ok": True, "product_family": product_family,
            "delivery_lead_days": body.packing_days + body.transport_days + body.buffer_days}
