"""Prototype-faithful dashboard KPIs.

Mirrors the control-tower prototype: every KPI is derived from ONE consistent
per-order status classification (on / risk / delay / crit), computed by the
existing deviation engine's compute_order_status. This keeps the six KPIs
internally consistent and lets each one power a drill-down list of the exact
orders behind the number, with their risk-reason chips.

KPIs (matching the prototype definitions/labels):
  - schedule_adherence_pct : on-track / total * 100        ("vs 95% target")
  - on_time_delivery_pct   : committed >= planned_delivery / total * 100  ("customer promise")
  - orders_at_risk         : count of 'risk' bucket        ("of N active")
  - delayed_critical       : count of 'delay' + 'crit'     ("need recovery")
  - material_at_risk       : material_status late/risk      ("orders affected")
  - capacity_conflicts     : overloaded work-centre-days    ("overloaded WC-days")
"""
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import models
from .deviation import compute_order_status, _thr


def _thresholds(db: Session) -> dict:
    return {
        "crit_slip_hrs": _thr(db, "crit_slip_hrs", 8),
        "delay_slip_hrs": _thr(db, "delay_slip_hrs", 2),
        "risk_slip_hrs": _thr(db, "risk_slip_hrs", 0.5),
        "buffer_crit_pct": _thr(db, "buffer_crit_pct", 20),
    }


def classify_orders(db: Session, now: datetime | None = None) -> dict:
    """Classify every order into on/risk/delay/crit buckets using the same
    per-order status computation the deviation engine uses. Orders without a
    current schedule are treated as unscheduled and excluded from bucket math
    (matching the prototype, which only classifies scheduled orders)."""
    now = now or datetime.now(timezone.utc)
    thresholds = _thresholds(db)
    buckets = {"on": [], "risk": [], "delay": [], "crit": []}
    details = {}  # order_id -> status detail for drill-downs
    adherent_count = 0
    unconfirmed = []  # "on" per status, but not adherent -- the watch list
    orders = db.query(models.OrderHeader).all()
    for o in orders:
        comp = compute_order_status(db, o, now, thresholds)
        if comp is None:
            continue  # unscheduled
        buckets[comp.status].append(o)
        details[o.id] = comp
        if comp.adherent:
            adherent_count += 1
        if comp.unconfirmed:
            unconfirmed.append(o)
    return {"buckets": buckets, "details": details, "orders": orders,
            "adherent_count": adherent_count, "unconfirmed": unconfirmed}


def compute_kpis(db: Session, now: datetime | None = None) -> dict:
    """Derive all six prototype KPIs from the shared classification."""
    cls = classify_orders(db, now)
    b = cls["buckets"]
    total = len(cls["orders"])
    scheduled = sum(len(v) for v in b.values())

    # Orders at risk = every order not on track (risk + delay + crit), so the
    # KPI number matches its drill-down list. (The prototype was internally
    # inconsistent here; this is the sensible, self-consistent choice.)
    at_risk = len(b["risk"]) + len(b["delay"]) + len(b["crit"])
    delayed_critical = len(b["delay"]) + len(b["crit"])

    # Adherence is DELIBERATELY a separate, more sensitive count than
    # on_track = total - at_risk. It uses the full slip (including a silent
    # start miss at full weight), so a not-yet-confirmed deviation dings
    # adherence immediately even while it's still too weak a signal to land
    # an order in "at risk" -- see compute_order_status's adherent field.
    # This means adherent_count + at_risk no longer necessarily sums to
    # total; that's intentional, not a bug.
    adherence_pct = round(100.0 * cls["adherent_count"] / total) if total else None

    # on-time delivery = committed >= planned_delivery / total
    otd_count = db.execute(text("""
        SELECT count(*) FROM planned_schedule ps
        JOIN order_header o ON o.id = ps.order_id
        WHERE ps.is_current
          AND o.committed_delivery_date::timestamptz >= ps.planned_delivery_dt
    """)).scalar() or 0
    otd_pct = round(100.0 * otd_count / total) if total else None

    material_at_risk = db.execute(text(
        "SELECT count(*) FROM material_status WHERE status IN ('late','risk')"
    )).scalar() or 0

    capacity_conflicts = db.execute(text(
        "SELECT count(*) FROM capacity_load WHERE overloaded"
    )).scalar() or 0

    return {
        "orders": total,
        "scheduled": scheduled,
        "schedule_adherence_pct": adherence_pct,   # vs 95% target
        "on_time_delivery_pct": otd_pct,           # customer promise
        "orders_at_risk": at_risk,                 # of N active
        "delayed_critical": delayed_critical,      # need recovery
        "unconfirmed": len(cls["unconfirmed"]),    # watch list -- too soft to act on individually
        "material_at_risk": material_at_risk,      # orders affected
        "capacity_conflicts": capacity_conflicts,  # overloaded WC-days
    }


def _order_row(o: models.OrderHeader, comp) -> dict:
    """Shape one drill-down row: order + slip/buffer + risk-reason chips."""
    return {
        "order_id": o.order_id,
        "product_id": o.product_id,
        "customer": o.customer,
        "priority": o.priority,
        "status": comp.status,
        "slip_hrs": comp.slip_hrs,
        "buffer_health": comp.buffer_health,
        "reasons": [{"type": r.kind, "text": r.text} for r in comp.reasons],
    }


def drilldown(db: Session, key: str, now: datetime | None = None) -> dict:
    """Return the order list behind a KPI, matching the prototype's modals.
    key in: adherence | risk | delayed | material | otd | capacity."""
    cls = classify_orders(db, now)
    b, details = cls["buckets"], cls["details"]

    def rows_for(orders):
        return [_order_row(o, details[o.id]) for o in orders if o.id in details]

    if key in ("adherence", "risk"):
        title = ("Schedule adherence - at-risk & off-plan orders"
                 if key == "adherence" else "Orders at risk")
        sub = "Orders not on track, with risk reasons"
        orders = b["risk"] + b["delay"] + b["crit"]
        return {"title": title, "subtitle": sub, "rows": rows_for(orders)}

    if key == "delayed":
        return {"title": "Delayed & critical orders",
                "subtitle": "Slip beyond delay threshold or delivery breach predicted",
                "rows": rows_for(b["delay"] + b["crit"])}

    if key == "unconfirmed":
        return {"title": "Unconfirmed - watch list",
                "subtitle": ("Real deviation too soft to act on individually -- a silent start "
                            "miss (however long) or a small delay under the at-risk threshold. "
                            "Not urgent; worth watching as a group."),
                "rows": rows_for(cls["unconfirmed"])}

    if key == "material":
        mats = db.execute(text("""
            SELECT o.order_id, o.product_id, o.customer, o.priority,
                   ms.status, ms.risk_reason, ms.slip_days
            FROM material_status ms JOIN order_header o ON o.id = ms.order_id
            WHERE ms.status IN ('late','risk') ORDER BY o.order_id
        """))
        rows = []
        for r in mats.fetchall():
            d = dict(zip(mats.keys(), r))
            reason = (f"Material late {d['slip_days']}d" if d["status"] == "late"
                      else (d["risk_reason"] or "Material at risk"))
            rows.append({
                "order_id": d["order_id"], "product_id": d["product_id"],
                "customer": d["customer"], "priority": d["priority"],
                "status": d["status"],
                "reasons": [{"type": "material", "text": reason}],
            })
        return {"title": "Material risk - orders with late/at-risk material",
                "subtitle": "Procurement delays cascading into production",
                "rows": rows}

    if key == "otd":
        res = db.execute(text("""
            SELECT o.order_id, o.product_id, o.customer, o.priority
            FROM planned_schedule ps JOIN order_header o ON o.id = ps.order_id
            WHERE ps.is_current
              AND ps.planned_delivery_dt > o.committed_delivery_date::timestamptz
            ORDER BY o.order_id
        """))
        rows = [dict(zip(res.keys(), r)) for r in res.fetchall()]
        return {"title": "On-time delivery - orders breaching committed date",
                "subtitle": "Forecast delivery later than committed", "rows": rows}

    if key == "capacity":
        res = db.execute(text("""
            SELECT work_center, load_date, demand_min, available_min
            FROM capacity_load WHERE overloaded
            ORDER BY load_date, work_center
        """))
        rows = [dict(zip(res.keys(), r)) for r in res.fetchall()]
        return {"title": "Capacity conflicts - overloaded work-centre days",
                "subtitle": "Days where scheduled demand exceeds available minutes",
                "rows": rows}

    return {"title": "Unknown", "subtitle": "", "rows": []}
