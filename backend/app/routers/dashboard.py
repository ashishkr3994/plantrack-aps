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


@router.get("/bottleneck-recommendations")
def bottleneck_recommendations(db: Session = Depends(get_db)):
    """Work centres that are structural bottlenecks, with a recommendation to
    add capacity (e.g. a second station). Analysis only; changes no schedule."""
    from ..engine.capacity import bottleneck_recommendations as _recs
    return _recs(db)


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
    """Prototype-faithful KPI set. All six KPIs are derived from ONE consistent
    per-order status classification (on/risk/delay/crit), matching the
    control-tower prototype. Falls back gracefully when nothing is scheduled."""
    from ..engine.kpi import compute_kpis
    out = compute_kpis(db)
    # products + open_alerts are cheap extras the dashboard also shows
    out["products"] = db.execute(text("SELECT count(*) FROM product")).scalar() or 0
    out["open_alerts"] = db.execute(
        text("SELECT count(*) FROM alert_log WHERE status='open'")).scalar() or 0
    # when the schedule state (capacity/deviation) was last recomputed -- lets
    # the UI show "schedule last updated N min ago" and avoid stale-view confusion
    out["last_updated"] = db.execute(
        text("SELECT MAX(computed_at) FROM capacity_load")).scalar()
    return out


@router.get("/kpi-drilldown/{key}")
def kpi_drilldown(key: str, db: Session = Depends(get_db)):
    """Orders behind a KPI, matching the prototype's click-through modals.
    key in: adherence | risk | delayed | material | otd | capacity.
    Each order row carries slip/buffer and risk-reason chips where applicable."""
    from ..engine.kpi import drilldown
    return drilldown(db, key)


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


@router.get("/capacity-cell")
def capacity_cell(work_center: str, load_date: str, db: Session = Depends(get_db)):
    """Which orders/operations load a given work-centre on a given day - the
    drill-down behind a heatmap cell. Shows what's breaching capacity there."""
    res = db.execute(text("""
        SELECT o.order_id, o.customer, o.priority,
               oo.operation_seq, oo.work_center, oo.duration_mins,
               oo.planned_start, oo.planned_end
        FROM order_operation oo
        JOIN order_header o ON o.id = oo.order_id
        WHERE oo.work_center = :wc
          AND oo.planned_start::date <= CAST(:d AS date)
          AND oo.planned_end::date   >= CAST(:d AS date)
        ORDER BY oo.planned_start
    """), {"wc": work_center, "d": load_date})
    cols = res.keys()
    operations = [
        {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(zip(cols, r)).items()}
        for r in res.fetchall()
    ]
    load = db.execute(text(
        "SELECT available_min, demand_min, round(load_pct,0) AS load_pct, overloaded "
        "FROM capacity_load WHERE work_center=:wc AND load_date=:d"),
        {"wc": work_center, "d": load_date}).mappings().first()
    return {
        "work_center": work_center,
        "load_date": load_date,
        "load": dict(load) if load else None,
        "operations": operations,
    }


@router.get("/delayed-orders")
def delayed_orders(db: Session = Depends(get_db)):
    """Every order with an open High/Critical deviation - the list behind the
    Delayed/Critical KPI drill-down. Each row carries its root cause so a
    planner can see *why* before deciding on a recovery action."""
    return _rows(db, """
        SELECT o.order_id, o.customer, o.priority, o.order_qty,
               o.committed_delivery_date,
               d.milestone_name, d.severity, d.root_cause_code,
               d.deviation_minutes, d.action_owner, d.generated_at
        FROM deviation_log d
        JOIN order_header o ON o.id = d.order_id
        WHERE d.resolution_status = 'Open' AND d.severity IN ('High','Critical')
        ORDER BY d.severity DESC, d.deviation_minutes DESC NULLS LAST
    """)
