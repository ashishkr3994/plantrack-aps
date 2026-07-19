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
import json

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
        return {"title": "Watch list - unconfirmed deviations",
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
        breach_pks = db.execute(text("""
            SELECT o.id FROM planned_schedule ps JOIN order_header o ON o.id = ps.order_id
            WHERE ps.is_current AND ps.planned_delivery_dt > o.committed_delivery_date::timestamptz
        """)).scalars().all()
        orders = [o for o in cls["orders"] if o.id in set(breach_pks)]
        return {"title": "On-time delivery - orders breaching committed date",
                "subtitle": "Forecast delivery later than committed", "rows": rows_for(orders)}

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


_TREND_KEYS = ["schedule_adherence_pct", "on_time_delivery_pct", "orders_at_risk",
               "delayed_critical", "unconfirmed", "material_at_risk", "capacity_conflicts"]


def record_snapshot(db: Session, kpis: dict, delayed_critical_order_ids: list[str]) -> None:
    """Record a KPI snapshot for trend/digest comparisons -- throttled to at
    most one per hour so repeated dashboard loads don't flood the table.
    Called from the /dashboard/kpis endpoint on every load; this is the only
    place snapshots get written, so history builds up naturally as the
    dashboard gets used rather than needing a separate scheduled job."""
    last = db.execute(text(
        "SELECT captured_at FROM dashboard_snapshot ORDER BY captured_at DESC LIMIT 1")).scalar()
    now = datetime.now(timezone.utc)
    if last is not None:
        last_aware = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
        if (now - last_aware).total_seconds() < 3600:
            return
    db.execute(text("""
        INSERT INTO dashboard_snapshot
            (captured_at, schedule_adherence_pct, on_time_delivery_pct, orders_at_risk,
             delayed_critical, unconfirmed, material_at_risk, capacity_conflicts,
             delayed_critical_order_ids)
        VALUES (:now, :sa, :otd, :risk, :dc, :unc, :mat, :cap, :ids)
    """), {
        "now": now, "sa": kpis.get("schedule_adherence_pct"), "otd": kpis.get("on_time_delivery_pct"),
        "risk": kpis.get("orders_at_risk"), "dc": kpis.get("delayed_critical"),
        "unc": kpis.get("unconfirmed"), "mat": kpis.get("material_at_risk"),
        "cap": kpis.get("capacity_conflicts"), "ids": json.dumps(delayed_critical_order_ids),
    })
    db.commit()


def get_trend(db: Session, current: dict) -> dict:
    """Delta for each KPI vs the closest snapshot to ~24h ago. Returns an
    empty dict (no trend shown) if there's no snapshot old enough yet -- a
    freshly reset demo or a brand-new deployment has no history to compare
    against, and showing a fake trend would be worse than showing none."""
    row = db.execute(text(f"""
        SELECT {', '.join(_TREND_KEYS)} FROM dashboard_snapshot
        WHERE captured_at <= now() - interval '20 hours'
        ORDER BY captured_at DESC LIMIT 1
    """)).mappings().first()
    if not row:
        return {}
    out = {}
    for k in _TREND_KEYS:
        if row[k] is not None and current.get(k) is not None:
            out[k] = current[k] - row[k]
    return out


def get_digest(db: Session, current_delayed_ids: list[str]) -> dict:
    """'Since you last checked': compares the current delayed/critical order
    set against the EARLIEST snapshot captured today (a "since this morning"
    baseline), so a planner opening the dashboard mid-shift sees what
    changed rather than just the current total. On the first load of the
    day there's no earlier snapshot yet, so this returns empty lists --
    honestly reflecting that there's nothing to compare against yet, not a
    fabricated zero."""
    row = db.execute(text("""
        SELECT delayed_critical_order_ids, captured_at FROM dashboard_snapshot
        WHERE captured_at::date = current_date
        ORDER BY captured_at ASC LIMIT 1
    """)).mappings().first()
    if not row:
        return {"new": [], "resolved": [], "since": None}
    prior_ids = set(row["delayed_critical_order_ids"] or [])
    current_ids = set(current_delayed_ids)
    return {
        "new": sorted(current_ids - prior_ids),
        "resolved": sorted(prior_ids - current_ids),
        "since": row["captured_at"].isoformat(),
    }
