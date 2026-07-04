"""Read-only dashboard endpoints backed by the schema's convenience views."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _rows(db, sql):
    res = db.execute(text(sql))
    cols = res.keys()
    return [dict(zip(cols, r)) for r in res.fetchall()]


@router.get("/watchlist")
def watchlist(db: Session = Depends(get_db)):
    """Order watchlist via v_order_watchlist (order + product + schedule + material)."""
    return _rows(db, "SELECT * FROM v_order_watchlist ORDER BY order_id")


@router.get("/capacity-conflicts")
def capacity_conflicts(db: Session = Depends(get_db)):
    return _rows(db, "SELECT * FROM v_capacity_conflicts")


@router.get("/open-alerts")
def open_alerts(db: Session = Depends(get_db)):
    return _rows(db, "SELECT * FROM v_open_alerts")


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    """A few headline counts for the dashboard KPI strip."""
    counts = {}
    for label, sql in {
        "orders": "SELECT count(*) FROM order_header",
        "products": "SELECT count(*) FROM product",
        "open_alerts": "SELECT count(*) FROM alert_log WHERE status='open'",
        "capacity_conflicts": "SELECT count(*) FROM capacity_load WHERE overloaded",
        "material_at_risk": "SELECT count(*) FROM material_status WHERE status IN ('late','risk')",
    }.items():
        counts[label] = db.execute(text(sql)).scalar()
    return counts
