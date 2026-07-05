"""Data-model browser: list all tables with live row counts, and page through
the rows of any table. Read-only. Table names are whitelisted to prevent any
SQL injection via the table parameter."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db

router = APIRouter(prefix="/datamodel", tags=["datamodel"])

# Whitelist of browsable tables with a short human description.
TABLES = {
    "plant": "Plants / sites",
    "plant_calendar": "Working shifts & holidays per plant",
    "lead_time_master": "Lead-time offsets by product family",
    "product": "Finished products",
    "routing": "Process routings",
    "routing_operation": "Operations within each routing",
    "bom_line": "Bill-of-materials lines",
    "order_header": "Customer orders",
    "order_operation": "Scheduled operations per order",
    "planned_schedule": "Planned schedule versions",
    "material_status": "Material readiness per order",
    "actual_event": "Logged execution events",
    "capacity_load": "Work-centre load per day",
    "deviation_log": "Detected deviations",
    "alert_log": "Raised alerts",
    "alert_threshold": "Alert threshold config",
    "reschedule_log": "Recovery / replan history",
    "solve_job": "Solver job runs",
    "app_user": "Users",
    "audit_log": "Audit trail",
}


@router.get("/tables")
def list_tables(db: Session = Depends(get_db)):
    """All browsable tables with a live row count."""
    out = []
    for name, desc in TABLES.items():
        try:
            n = db.execute(text(f"SELECT count(*) FROM {name}")).scalar()
        except Exception:
            n = None
        out.append({"table": name, "description": desc, "row_count": n})
    return out


@router.get("/rows/{table}")
def table_rows(table: str, limit: int = 200, offset: int = 0,
               db: Session = Depends(get_db)):
    """Rows of a whitelisted table (most recent first where an id exists)."""
    if table not in TABLES:
        raise HTTPException(404, f"unknown or non-browsable table '{table}'")
    limit = max(1, min(limit, 1000))
    order = "ORDER BY id DESC" if _has_id(db, table) else ""
    res = db.execute(text(f"SELECT * FROM {table} {order} LIMIT :lim OFFSET :off"),
                     {"lim": limit, "off": offset})
    cols = list(res.keys())
    rows = [
        {k: (v.isoformat() if hasattr(v, "isoformat") else v)
         for k, v in dict(zip(cols, r)).items()}
        for r in res.fetchall()
    ]
    total = db.execute(text(f"SELECT count(*) FROM {table}")).scalar()
    return {"table": table, "columns": cols, "rows": rows, "total": total,
            "limit": limit, "offset": offset}


def _has_id(db: Session, table: str) -> bool:
    q = db.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name=:t AND column_name='id' LIMIT 1"), {"t": table}).first()
    return q is not None
