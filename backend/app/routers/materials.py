"""Material status + risk endpoints.

Exposes per-order material readiness and lets a planner trigger a re-evaluation
of time-based risk (this also runs automatically on material_ready events and
should be run on a schedule in production).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..deps import require_role
from ..engine.material_init import ensure_material_status
from ..engine.material_risk import evaluate_material_risk

router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("/status")
def material_status(db: Session = Depends(get_db)):
    """Per-order material readiness joined with the order's business id."""
    rows = (db.query(models.MaterialStatus, models.OrderHeader)
              .join(models.OrderHeader, models.OrderHeader.id == models.MaterialStatus.order_id)
              .order_by(models.OrderHeader.order_id).all())
    out = []
    for ms, o in rows:
        out.append({
            "order_id": o.order_id,
            "material_count": ms.material_count,
            "max_lead_days": ms.max_lead_days,
            "planned_ready_dt": ms.planned_ready_dt.isoformat() if ms.planned_ready_dt else None,
            "actual_ready_dt": ms.actual_ready_dt.isoformat() if ms.actual_ready_dt else None,
            "status": ms.status,
            "slip_days": float(ms.slip_days or 0),
            "risk_reason": ms.risk_reason,
        })
    return out


@router.post("/evaluate-risk")
def evaluate_risk(_: models.AppUser = Depends(require_role("planner")),
                  db: Session = Depends(get_db)):
    """Recompute time-based material risk for all orders. Returns status counts."""
    ensure_material_status(db)
    counts = evaluate_material_risk(db)
    return {"counts": counts}
