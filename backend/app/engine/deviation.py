"""Deviation & alert engine — server-side port of the prototype's
computeOrderStatus + generateAlerts.

Compares actual execution (hand-logged events) against the current baseline
schedule for each order, derives a forecast slip from multiple signals, classifies
order health, and raises role-targeted alerts. Writes deviation_log and alert_log.

Signals (mirroring the prototype):
  1. Late start (actual start vs planned start)
  2. Silent start miss (planned start passed, no start event)
  3. Downtime accumulation (pause events)
  4. Scrap rework (scrap qty -> extra run time)
  5. Material delay (material_status late/risk)
  6. Throughput / run-rate shortfall (partial completes vs required rate)
  7. Buffer erosion (remaining buffer vs original)
  8. Capacity overload touching the order

Role ownership (who each alert escalates to):
  - material late          -> procurement
  - silent start miss      -> supervisor
  - buffer erosion         -> planner
  - capacity overload      -> planner
  - delivery promise breach-> supervisor (sales/account proxy)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import text

from .. import models
from ..events_bus import publish


@dataclass
class Reason:
    kind: str       # 'time' | 'buffer' | 'capacity' | 'material'
    text: str


@dataclass
class OrderStatus:
    order_pk: int
    order_id: str
    status: str             # 'on' | 'risk' | 'delay' | 'crit'
    slip_hrs: float
    buffer_health: int
    remaining_buffer: float
    forecast_end: datetime | None
    reasons: list[Reason] = field(default_factory=list)


# alert dedup_key prefix -> (alert_type, owner role, title prefix)
OWNER = {
    "mat-late": ("warn", "procurement"),
    "silent": ("crit", "supervisor"),
    "buffer": ("warn", "planner"),
    "cap": ("warn", "planner"),
    "breach": ("crit", "supervisor"),
    "mat-risk": ("warn", "procurement"),
}


def _thr(db: Session, key: str, default: float) -> float:
    row = db.query(models.AlertThreshold).filter_by(threshold_key=key).first()
    return float(row.value) if row else default


def _aware(dt):
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def compute_order_status(db: Session, order: models.OrderHeader, now: datetime,
                         thresholds: dict) -> OrderStatus | None:
    sched = (db.query(models.PlannedSchedule)
               .filter_by(order_id=order.id, is_current=True).first())
    if not sched:
        return None

    reasons: list[Reason] = []
    events = (db.query(models.ActualEvent)
                .filter_by(order_id=order.id)
                .order_by(models.ActualEvent.event_timestamp).all())
    planned_start = _aware(sched.planned_prod_start_dt)
    planned_end = _aware(sched.planned_prod_end_dt)
    slip_mins = 0.0

    start_evs = [e for e in events if e.event_type == "start"]
    has_started = len(start_evs) > 0
    has_completed = any(e.event_type in ("complete", "dispatch", "delivered") for e in events)

    # 1. late start
    if start_evs:
        actual_start = _aware(start_evs[-1].event_timestamp)
        start_slip = (actual_start - planned_start).total_seconds() / 60
        if start_slip > 0:
            slip_mins += start_slip
            reasons.append(Reason("time", f"Late start +{round(start_slip)}m"))

    # 2. silent start miss
    if not has_started and not has_completed and now > planned_start:
        silent = (now - planned_start).total_seconds() / 60
        slip_mins += silent
        reasons.append(Reason("time", f"Silent start miss +{round(silent/60, 1)}h"))

    # 3. downtime
    downtime = sum(int(e.downtime_mins or 0) for e in events if e.event_type == "pause")
    if downtime > 0:
        slip_mins += downtime
        reasons.append(Reason("time", f"Downtime {downtime}m"))

    # 4. scrap rework
    scrap_qty = sum(int(e.event_qty or 0) for e in events if e.event_type == "scrap")
    if scrap_qty > 0:
        product = db.get(models.Product, order.product_id)
        avg_run = 0.0
        if product and product.routing:
            avg_run = sum(float(op.run_per_unit_min or 0) for op in product.routing.operations)
        rework = scrap_qty * avg_run
        slip_mins += rework
        reasons.append(Reason("material", f"{scrap_qty} scrap -> +{round(rework/60, 1)}h rework"))

    # 5. material delay
    ms = db.query(models.MaterialStatus).filter_by(order_id=order.id).first()
    if ms and ms.status == "late":
        reasons.append(Reason("material", f"Material late {ms.slip_days}d"))
    elif ms and ms.status == "risk":
        reasons.append(Reason("material", ms.risk_reason or "Material at risk"))

    # 6. throughput / run rate
    complete_evs = [e for e in events if e.event_type == "complete" and e.event_qty]
    if has_started and not has_completed and complete_evs:
        completed_qty = sum(int(e.event_qty or 0) for e in complete_evs)
        first_start = _aware(start_evs[0].event_timestamp)
        elapsed_min = (now - first_start).total_seconds() / 60
        actual_rate = completed_qty / elapsed_min if elapsed_min > 0 else 0
        remaining_qty = int(order.order_qty) - completed_qty - scrap_qty
        remaining_plan_min = (planned_end - now).total_seconds() / 60
        required_rate = remaining_qty / remaining_plan_min if remaining_plan_min > 0 else 999
        if actual_rate > 0 and actual_rate < required_rate * 0.9:
            reasons.append(Reason("time", f"Run rate {round(actual_rate/required_rate*100)}% of needed"))
            proj_extra = remaining_qty / actual_rate - remaining_plan_min
            if proj_extra > 0:
                slip_mins += proj_extra

    forecast_end = datetime.fromtimestamp(planned_end.timestamp() + slip_mins * 60, tz=timezone.utc)
    slip_hrs = max(0, round((forecast_end - planned_end).total_seconds() / 3600, 1))

    # 7. buffer erosion
    orig_buffer = float(sched.original_buffer_hrs or sched.buffer_hrs or 0)
    remaining_buffer = orig_buffer - slip_hrs
    buffer_health = round(remaining_buffer / orig_buffer * 100) if orig_buffer > 0 else (100 if slip_hrs == 0 else -1)
    buf_crit = thresholds["buffer_crit_pct"]
    if orig_buffer > 0 and 0 <= buffer_health < buf_crit:
        reasons.append(Reason("buffer", f"Buffer {buffer_health}% left"))

    # 8. capacity overload affecting this order
    hits_overload = bool(db.execute(text("""
        SELECT 1 FROM order_operation oo
        JOIN capacity_load cl ON cl.work_center = oo.work_center
            AND cl.load_date = (oo.planned_start AT TIME ZONE 'UTC')::date
            AND cl.overloaded
        WHERE oo.order_id = :oid LIMIT 1
    """), {"oid": order.id}).first())
    if hits_overload:
        reasons.append(Reason("capacity", "Capacity overload"))

    # classify
    status = "on"
    delivery_breach = remaining_buffer < 0
    if has_completed:
        status, slip_hrs = "on", 0
    elif slip_hrs > thresholds["crit_slip_hrs"] or delivery_breach:
        status = "crit"
    elif slip_hrs > thresholds["delay_slip_hrs"]:
        status = "delay"
    elif (slip_hrs > thresholds["risk_slip_hrs"] or buffer_health < buf_crit
          or hits_overload or (ms and ms.status in ("late", "risk"))):
        status = "risk"

    return OrderStatus(
        order_pk=order.id, order_id=order.order_id, status=status, slip_hrs=slip_hrs,
        buffer_health=buffer_health, remaining_buffer=remaining_buffer,
        forecast_end=forecast_end, reasons=reasons)


def run_deviation_engine(db: Session, now: datetime | None = None) -> dict:
    """Recompute deviations + alerts for all orders with a current schedule.
    Preserves ack/closed status across regeneration (dedup by key)."""
    now = now or datetime.now(timezone.utc)
    thresholds = {
        "crit_slip_hrs": _thr(db, "crit_slip_hrs", 8),
        "delay_slip_hrs": _thr(db, "delay_slip_hrs", 2),
        "risk_slip_hrs": _thr(db, "risk_slip_hrs", 0.5),
        "buffer_crit_pct": _thr(db, "buffer_crit_pct", 20),
    }

    # preserve prior alert status
    prev_status = {a.dedup_key: a.status for a in db.query(models.AlertLog).all()}

    # clear and regenerate (deviation_log fully, alert_log re-derived)
    db.execute(text("DELETE FROM alert_log"))
    db.execute(text("DELETE FROM deviation_log"))
    db.commit()

    alerts_made = 0
    deviations_made = 0
    status_counts = {"on": 0, "risk": 0, "delay": 0, "crit": 0}

    def push_alert(atype, order_pk, dedup_key, title, meta):
        nonlocal alerts_made
        db.add(models.AlertLog(
            alert_id=f"ALT-{dedup_key}", dedup_key=dedup_key, alert_type=atype,
            order_id=order_pk, title=title, meta=meta,
            status=prev_status.get(dedup_key, "open"), raised_at=now))
        alerts_made += 1

    orders = db.query(models.OrderHeader).all()
    for order in orders:
        comp = compute_order_status(db, order, now, thresholds)
        if comp is None:
            continue
        status_counts[comp.status] = status_counts.get(comp.status, 0) + 1
        ms = db.query(models.MaterialStatus).filter_by(order_id=order.id).first()
        product = db.get(models.Product, order.product_id)
        pname = product.name if product else order.order_id

        # deviation_log: one row capturing the production-end forecast deviation
        sched = (db.query(models.PlannedSchedule)
                   .filter_by(order_id=order.id, is_current=True).first())
        if comp.slip_hrs > 0 and sched:
            sev = "Critical" if comp.status == "crit" else "High" if comp.status == "delay" else "Medium"
            owner = "Production supervisor"
            cause = comp.reasons[0].text if comp.reasons else "Forecast slip"
            db.add(models.DeviationLog(
                deviation_id=f"DEV-{order.order_id}-PROD", order_id=order.id,
                milestone_name="Production end",
                baseline_dt=sched.planned_prod_end_dt, latest_forecast_dt=comp.forecast_end,
                deviation_minutes=round(comp.slip_hrs * 60, 2), severity=sev,
                root_cause_code=cause, action_owner=owner, resolution_status="Open",
                generated_at=now))
            deviations_made += 1

        # alerts (role-targeted)
        if ms and ms.status == "late":
            push_alert("warn", order.id, f"mat-late-{order.order_id}",
                       f"Material late {ms.slip_days}d — {pname}",
                       "Owner: Procurement lead · cascaded into production")
        elif ms and ms.status == "risk":
            push_alert("warn", order.id, f"mat-risk-{order.order_id}",
                       f"Material at risk — {pname}",
                       f"{ms.risk_reason or 'Approaching ready date'} · Owner: Procurement lead")

        for r in comp.reasons:
            if r.kind == "time" and "Silent" in r.text:
                push_alert("crit", order.id, f"silent-{order.order_id}",
                           f"Silent start miss — {pname}", f"{r.text} · Owner: Production supervisor")
            elif r.kind == "buffer":
                push_alert("warn", order.id, f"buffer-{order.order_id}",
                           f"Buffer erosion — {pname}", f"{r.text} · Owner: Planner")
            elif r.kind == "capacity":
                push_alert("warn", order.id, f"cap-{order.order_id}",
                           f"Capacity overload — {pname}",
                           "A work center for this order is overloaded · Owner: Planner")

        if comp.status == "crit":
            push_alert("crit", order.id, f"breach-{order.order_id}",
                       f"Delivery promise at risk — {pname}",
                       f"Forecast +{comp.slip_hrs}h · buffer {comp.buffer_health}% · Owner: Supervisor + Sales")

    db.commit()
    if alerts_made:
        publish("alert_raised", {"count": alerts_made})
    return {"alerts": alerts_made, "deviations": deviations_made, "status_counts": status_counts}
