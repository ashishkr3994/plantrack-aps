"""Alerts & deviations API.

Lists role-relevant alerts (so procurement sees material alerts, supervisors see
start-miss/breach alerts, planners see buffer/capacity alerts), lets users
acknowledge/close them, exposes the deviation log, and lets a planner re-run the
deviation engine on demand (it also runs automatically after each solve).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..deps import require_role, get_current_user, audit
from ..engine.deviation import run_deviation_engine
from ..engine.capacity import compute_capacity_load

router = APIRouter(prefix="/alerts", tags=["alerts"])

# which alert dedup-key prefixes each role cares about (for "my alerts" filtering)
ROLE_ALERT_PREFIXES = {
    "procurement": ("mat-late", "mat-risk"),
    "supervisor": ("silent", "breach"),
    "planner": ("buffer", "cap", "silent", "breach", "mat-late", "mat-risk"),
    "admin": None,   # all
    "viewer": None,  # all (read-only)
}


def _alert_dict(a: models.AlertLog) -> dict:
    return {
        "alert_id": a.alert_id, "dedup_key": a.dedup_key, "alert_type": a.alert_type,
        "title": a.title, "meta": a.meta, "status": a.status,
        "raised_at": a.raised_at.isoformat() if a.raised_at else None,
    }


@router.get("")
def list_alerts(mine: bool = False, status: str | None = None,
                user: models.AppUser = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """List alerts. `mine=true` filters to the caller's role ownership."""
    q = db.query(models.AlertLog)
    if status:
        q = q.filter(models.AlertLog.status == status)
    alerts = q.order_by(models.AlertLog.raised_at.desc()).all()
    if mine:
        prefixes = ROLE_ALERT_PREFIXES.get(user.role)
        if prefixes is not None:
            alerts = [a for a in alerts if a.dedup_key.startswith(prefixes)]
    return [_alert_dict(a) for a in alerts]


@router.post("/{dedup_key}/ack")
def ack_alert(dedup_key: str, user: models.AppUser = Depends(get_current_user),
              db: Session = Depends(get_db)):
    a = db.query(models.AlertLog).filter_by(dedup_key=dedup_key).first()
    if not a:
        raise HTTPException(404, "alert not found")
    a.status = "ack"
    a.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    audit(db, user, "ack_alert", "alert", dedup_key)
    return _alert_dict(a)


@router.post("/{dedup_key}/close")
def close_alert(dedup_key: str, user: models.AppUser = Depends(get_current_user),
                db: Session = Depends(get_db)):
    a = db.query(models.AlertLog).filter_by(dedup_key=dedup_key).first()
    if not a:
        raise HTTPException(404, "alert not found")
    a.status = "closed"
    a.closed_at = datetime.now(timezone.utc)
    db.commit()
    audit(db, user, "close_alert", "alert", dedup_key)
    return _alert_dict(a)


@router.get("/deviations")
def list_deviations(db: Session = Depends(get_db)):
    rows = (db.query(models.DeviationLog)
              .order_by(models.DeviationLog.deviation_minutes.desc()).all())
    return [{
        "deviation_id": d.deviation_id, "order_id": d.order_id,
        "milestone_name": d.milestone_name,
        "baseline_dt": d.baseline_dt.isoformat() if d.baseline_dt else None,
        "latest_forecast_dt": d.latest_forecast_dt.isoformat() if d.latest_forecast_dt else None,
        "deviation_minutes": float(d.deviation_minutes or 0), "severity": d.severity,
        "root_cause_code": d.root_cause_code, "action_owner": d.action_owner,
        "resolution_status": d.resolution_status,
    } for d in rows]


@router.post("/run-engine")
def run_engine(_: models.AppUser = Depends(require_role("planner")),
               db: Session = Depends(get_db)):
    """Recompute capacity load + deviations + alerts on demand."""
    cap = compute_capacity_load(db)
    dev = run_deviation_engine(db)
    return {"capacity": cap, "deviation": dev}