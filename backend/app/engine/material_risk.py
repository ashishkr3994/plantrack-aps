"""Time-based material risk evaluation — ported from the prototype's
evaluateMaterialRisk.

For every order awaiting material (no confirmed arrival), this flags risk
PROACTIVELY based on elapsed/approaching time, rather than waiting for a late
arrival event:

  * planned_ready_dt already passed, still no actual arrival  -> 'late'
  * planned_ready_dt within the material-risk window (default 3 days), no
    confirmed arrival                                          -> 'risk'
  * confirmed arrival on/before planned                        -> 'ready'
  * confirmed arrival after planned                            -> 'late' (slip recorded)

The risk window comes from the alert_threshold 'mat_risk_window_days'.
This is intended to run on a schedule (and after any event/import) so the
Material-at-risk KPI lights up before anything is logged late.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from .. import models


def _threshold_days(db: Session, key: str, default: float) -> float:
    row = db.query(models.AlertThreshold).filter_by(threshold_key=key).first()
    return float(row.value) if row else default


def evaluate_material_risk(db: Session, now: datetime | None = None) -> dict:
    """Recompute status for all material_status rows. Returns a summary count."""
    now = now or datetime.now(timezone.utc)
    window_days = _threshold_days(db, "mat_risk_window_days", 3)
    window = timedelta(days=window_days)

    counts = {"ready": 0, "risk": 0, "late": 0, "ordered": 0}
    rows = db.query(models.MaterialStatus).all()
    for ms in rows:
        planned = ms.planned_ready_dt
        actual = ms.actual_ready_dt
        if planned is not None and planned.tzinfo is None:
            planned = planned.replace(tzinfo=timezone.utc)
        if actual is not None and actual.tzinfo is None:
            actual = actual.replace(tzinfo=timezone.utc)

        if actual is not None:
            # arrival confirmed: ready if on time, else late with slip
            if planned is not None and actual > planned:
                ms.status = "late"
                ms.slip_days = round((actual - planned).total_seconds() / 86400, 2)
                ms.risk_reason = "Material arrived late"
            else:
                ms.status = "ready"
                ms.slip_days = 0
                ms.risk_reason = None
        elif planned is not None:
            if now > planned:
                # planned ready date passed, nothing logged -> silent late
                ms.status = "late"
                ms.slip_days = round((now - planned).total_seconds() / 86400, 2)
                ms.risk_reason = "Planned material-ready date passed with no confirmed arrival"
            elif planned - now <= window:
                # approaching, unconfirmed -> proactive risk
                ms.status = "risk"
                ms.slip_days = 0
                ms.risk_reason = f"Material due within {int(window_days)} day(s), no arrival confirmed"
            else:
                ms.status = "ordered"
                ms.slip_days = 0
                ms.risk_reason = None
        else:
            ms.status = "ordered"
            ms.risk_reason = None

        counts[ms.status] = counts.get(ms.status, 0) + 1
    db.commit()
    return counts
