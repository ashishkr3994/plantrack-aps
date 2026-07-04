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


@router.get("/kpis")
def kpis(db: Session = Depends(get_db)):
    """Richer KPI set for the dashboard: adherence, on-time delivery, risk counts.
    Falls back gracefully when there is no schedule yet."""
    def scalar(sql, default=0):
        v = db.execute(text(sql)).scalar()
        return v if v is not None else default

    orders_total = scalar("SELECT count(*) FROM order_header")
    products = scalar("SELECT count(*) FROM product")
    open_alerts = scalar("SELECT count(*) FROM alert_log WHERE status='open'")
    capacity_conflicts = scalar("SELECT count(*) FROM capacity_load WHERE overloaded")
    material_at_risk = scalar("SELECT count(*) FROM material_status WHERE status IN ('late','risk')")

    # scheduled orders (current baseline)
    scheduled = scalar("SELECT count(*) FROM planned_schedule WHERE is_current")
    # on-time = current schedule delivers on/before committed date
    on_time = scalar("""
        SELECT count(*) FROM planned_schedule ps
        JOIN order_header o ON o.id = ps.order_id
        WHERE ps.is_current AND ps.planned_delivery_dt <= o.committed_delivery_date::timestamptz + interval '1 day'
    """)
    # delayed / critical from open deviations
    delayed = scalar("SELECT count(DISTINCT order_id) FROM deviation_log WHERE resolution_status='Open' AND severity IN ('High','Critical')")

    otd_pct = round(100.0 * on_time / scheduled) if scheduled else None
    # schedule adherence = scheduled orders that are not stale
    not_stale = scalar("SELECT count(*) FROM planned_schedule WHERE is_current AND NOT is_stale")
    adherence_pct = round(100.0 * not_stale / scheduled) if scheduled else None
    at_risk = material_at_risk + delayed

    return {
        "orders": orders_total,
        "products": products,
        "scheduled": scheduled,
        "schedule_adherence_pct": adherence_pct,
        "on_time_delivery_pct": otd_pct,
        "orders_at_risk": at_risk,
        "delayed_critical": delayed,
        "material_at_risk": material_at_risk,
        "capacity_conflicts": capacity_conflicts,
        "open_alerts": open_alerts,
    }


@router.get("/delay-reasons")
def delay_reasons(db: Session = Depends(get_db)):
    """Root-cause distribution of open deviations, for the delay-reasons panel."""
    return _rows(db, """
        SELECT COALESCE(root_cause_code, 'Unclassified') AS root_cause,
               count(*) AS count,
               round(sum(deviation_minutes)/60.0, 1) AS total_hours
        FROM deviation_log
        WHERE resolution_status = 'Open'
        GROUP BY COALESCE(root_cause_code, 'Unclassified')
        ORDER BY count DESC
    """)


@router.get("/recovery-pipeline")
def recovery_pipeline(db: Session = Depends(get_db)):
    """Orders that have been recovered/replanned, most recent first."""
    return _rows(db, """
        SELECT o.order_id, o.customer, rl.version, rl.performed_by,
               rl.performed_at, rl.baseline_delivery, rl.new_delivery
        FROM reschedule_log rl
        JOIN order_header o ON o.id = rl.order_id
        ORDER BY rl.performed_at DESC NULLS LAST
        LIMIT 25
    """)


@router.get("/capacity-heatmap")
def capacity_heatmap(db: Session = Depends(get_db)):
    """Per-work-centre, per-day load percentage for the heatmap grid."""
    rows = _rows(db, """
        SELECT work_center, load_date::text AS load_date,
               round(load_pct, 0) AS load_pct, overloaded
        FROM capacity_load
        ORDER BY work_center, load_date
    """)
    work_centers = sorted({r["work_center"] for r in rows})
    dates = sorted({r["load_date"] for r in rows})
    cell = {(r["work_center"], r["load_date"]): r for r in rows}
    grid = []
    for wc in work_centers:
        grid.append({
            "work_center": wc,
            "cells": [
                {
                    "date": d,
                    "load_pct": float(cell[(wc, d)]["load_pct"]) if (wc, d) in cell else None,
                    "overloaded": cell[(wc, d)]["overloaded"] if (wc, d) in cell else False,
                }
                for d in dates
            ],
        })
    return {"work_centers": work_centers, "dates": dates, "grid": grid}


@router.get("/order-detail/{order_id}")
def order_detail(order_id: str, db: Session = Depends(get_db)):
    """Everything about one order for the drill-down: status, schedule,
    risk signals, material & BOM, operation sequence, execution events."""
    o = db.execute(text("SELECT * FROM order_header WHERE order_id=:oid"),
                   {"oid": order_id}).mappings().first()
    if not o:
        from fastapi import HTTPException
        raise HTTPException(404, "order not found")
    opk = o["id"]
    product = db.execute(text("SELECT * FROM product WHERE id=:p"),
                         {"p": o["product_id"]}).mappings().first()

    schedule = db.execute(text(
        "SELECT * FROM planned_schedule WHERE order_id=:o AND is_current"),
        {"o": opk}).mappings().first()

    operations = _rows(db, f"""
        SELECT operation_seq, work_center, parallel_group,
               predecessor_operation_seq, planned_start, planned_end, duration_mins
        FROM order_operation WHERE order_id={opk} ORDER BY operation_seq
    """)

    risk_signals = _rows(db, f"""
        SELECT deviation_id, milestone_name, severity, root_cause_code,
               action_owner, resolution_status, deviation_minutes, generated_at
        FROM deviation_log WHERE order_id={opk}
        ORDER BY generated_at DESC
    """)

    material = db.execute(text("SELECT * FROM material_status WHERE order_id=:o"),
                          {"o": opk}).mappings().first()
    bom = _rows(db, f"""
        SELECT material, qty_per_unit, uom, supplier, lead_days
        FROM bom_line WHERE product_id={o['product_id']} ORDER BY id
    """)

    events = _rows(db, f"""
        SELECT event_type, event_timestamp, operation_seq, event_qty,
               downtime_reason, downtime_mins, entered_by
        FROM actual_event WHERE order_id={opk} ORDER BY event_timestamp
    """)

    def to_out(m):
        return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(m).items()} if m else None

    return {
        "order": to_out(o),
        "product": to_out(product),
        "schedule": to_out(schedule),
        "operations": operations,
        "risk_signals": risk_signals,
        "material": to_out(material),
        "bom": bom,
        "events": events,
    }
