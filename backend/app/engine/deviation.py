"""Deviation & alert engine - server-side port of the prototype's
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
from .downtime_utils import pair_pause_resume, earliest_effective_start


@dataclass
class Reason:
    kind: str       # 'time' | 'buffer' | 'capacity' | 'material'
    text: str


@dataclass
class OrderStatus:
    order_pk: int
    order_id: str
    status: str             # 'on' | 'risk' | 'delay' | 'crit' -- gates at-risk/delayed-critical
    adherent: bool          # true only if slip_hrs (full, including silent) is within tolerance
                            # -- deliberately MORE sensitive than status, so a silent start miss
                            # dings schedule adherence immediately even though it never counts
                            # toward at-risk/delayed-critical (see compute_order_status).
    unconfirmed: bool       # on-track per status, but not adherent -- the "watch list": real
                            # deviation too soft (or, for a silent start miss, too unconfirmed)
                            # to count as at-risk, but worth seeing as a group.
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


def _material_still_unresolved(ms: "models.MaterialStatus") -> bool:
    """A material status of 'late' covers two different situations that share
    the same string: (a) still missing -- planned ready date passed and
    nothing confirmed -- a real, ongoing problem, or (b) confirmed ready, just
    later than planned -- a resolved historical fact. Only (a) should keep an
    order flagged at-risk; once actual_ready_dt is set, the material IS here,
    however tardy, and shouldn't block the order's health forever. status
    stays 'late' either way, correctly preserving the historical record."""
    if ms.status == "risk":
        return True
    if ms.status == "late":
        return ms.actual_ready_dt is None
    return False


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
    silent_mins = 0.0  # tracked separately -- see thresholds dict for why

    effective_start = earliest_effective_start(events)  # (event, ts) or None, start OR resume
    has_started = effective_start is not None
    completion_evs = [e for e in events if e.event_type in ("complete", "dispatch", "delivered")]
    has_completed = len(completion_evs) > 0
    # The LATEST of these -- e.g. "complete" logged, then "dispatch" a day
    # later -- is the real-world moment the order was actually finished with,
    # used below to check the completion against the committed date instead
    # of assuming a completed order is automatically on time.
    actual_completion_ts = _aware(max(e.event_timestamp for e in completion_evs)) if completion_evs else None

    # 1. late start -- an explicit start event, OR a resume standing in for
    # one when no start was ever logged. Resuming implies production is now
    # actually running even if a distinct "start" was never separately
    # logged (e.g. an order sat idle before anyone got to it, and the first
    # thing recorded is a resume once work actually began).
    if effective_start:
        start_ev, start_ts = effective_start
        actual_start = _aware(start_ts)
        start_slip = (actual_start - planned_start).total_seconds() / 60
        if start_slip > 0:
            slip_mins += start_slip
            label = "Late start" if start_ev.event_type == "start" else "Late start (via resume)"
            reasons.append(Reason("time", f"{label} +{round(start_slip)}m"))

    # 2. silent start miss -- unchanged in spirit: only fires when NEITHER a
    # start NOR a resume has ever been logged for this order.
    if not has_started and not has_completed and now > planned_start:
        silent = (now - planned_start).total_seconds() / 60
        slip_mins += silent
        silent_mins += silent
        reasons.append(Reason("time", f"Silent start miss +{round(silent/60, 1)}h"))

    # 3. downtime -- real elapsed time (resume_ts - pause_ts) once a matching
    # resume has been logged; the planner's original estimate only while a
    # pause is still ongoing (see downtime_utils.pair_pause_resume).
    downtime_windows = pair_pause_resume(events)
    downtime = sum(w.duration_mins for w in downtime_windows)
    if downtime > 0:
        slip_mins += downtime
        still_open = any(not w.resumed for w in downtime_windows)
        suffix = " (ongoing)" if still_open else ""
        reasons.append(Reason("time", f"Downtime {round(downtime)}m{suffix}"))

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
        first_start = _aware(effective_start[1]) if effective_start else now
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

    # 6b. schedule lateness: does the plan DELIVER past the committed date?
    # The solver now targets production finishing early enough that delivery
    # (prod_end + fixed pack/dispatch/transport lead) lands by the committed
    # date, so comparing delivery vs committed is consistent with the solver's
    # own on-time basis. An order only counts late here if delivery itself
    # slips past the committed day.
    sched_late_hrs = 0.0
    if sched.planned_delivery_dt is not None:
        committed_eod = _aware(datetime(
            order.committed_delivery_date.year,
            order.committed_delivery_date.month,
            order.committed_delivery_date.day, 23, 59))
        plan_delivery = _aware(sched.planned_delivery_dt)
        if plan_delivery > committed_eod:
            sched_late_hrs = round((plan_delivery - committed_eod).total_seconds() / 3600, 1)
            reasons.append(Reason("time", f"Delivery {sched_late_hrs}h past committed"))
    # the effective slip is the larger of event-driven and plan-driven lateness
    slip_hrs = max(slip_hrs, sched_late_hrs)

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
    # a real delivery breach = plan delivers past the END of the committed day
    # (consistent with sched_late_hrs; avoids flagging same-day deliveries that
    # merely land after midnight as "late").
    # For a completed order, the plan's own projected delivery (sched_late_hrs,
    # based on sched.planned_delivery_dt) is stale -- the order is done, so
    # whether it actually breached the committed date is what matters, not
    # what the plan once predicted. Computed again below once the real
    # completion timestamp is available; placeholder here for in-progress
    # orders, where the plan-based check is still the right one.
    delivery_breach = sched_late_hrs > 0

    # Status (Orders at risk / Delayed-critical) is driven ONLY by CONFIRMED
    # slip -- late start, downtime, scrap rework, throughput shortfall,
    # delivery breach, material status. A silent start miss NEVER contributes
    # here, however long it persists -- it's an unconfirmed signal (no logged
    # event at all), and this team would rather it sit on the Unconfirmed /
    # watch list indefinitely than eventually get treated as a confirmed
    # delay. slip_hrs itself (used for adherence, buffer, forecast) is
    # unaffected by this and still includes the full silent contribution.
    non_silent_slip_hrs = max(0.0, round((slip_mins - silent_mins) / 60, 1))
    escalation_hrs = max(non_silent_slip_hrs, sched_late_hrs)

    if has_completed:
        # A completed order's final health is determined by when it ACTUALLY
        # finished vs. the committed delivery date -- not assumed to be zero
        # slip just because something was logged. Verified this was a real
        # bug: completing an order 20 days past its committed date previously
        # still showed status="on" with no signals at all. in-progress
        # signals (silent start, throughput, capacity) no longer apply to a
        # finished order, but the one thing that still matters -- did it
        # actually make the promised date -- is checked for real here.
        committed_eod = _aware(datetime(
            order.committed_delivery_date.year,
            order.committed_delivery_date.month,
            order.committed_delivery_date.day, 23, 59))
        completion_slip_hrs = 0.0
        if actual_completion_ts and actual_completion_ts > committed_eod:
            completion_slip_hrs = round((actual_completion_ts - committed_eod).total_seconds() / 3600, 1)
            reasons.append(Reason("time", f"Completed {completion_slip_hrs}h past committed date"))
        slip_hrs = completion_slip_hrs
        delivery_breach = completion_slip_hrs > 0  # supersede the plan-based value above
        if completion_slip_hrs > thresholds["crit_slip_hrs"]:
            status = "crit"
        elif completion_slip_hrs > thresholds["delay_slip_hrs"]:
            status = "delay"
        elif completion_slip_hrs > 0:
            status = "risk"
        else:
            status = "on"
    elif escalation_hrs > thresholds["crit_slip_hrs"] or delivery_breach:
        status = "crit"
    elif escalation_hrs > thresholds["delay_slip_hrs"]:
        status = "delay"
    elif (escalation_hrs > thresholds["risk_slip_hrs"]
          or (ms and _material_still_unresolved(ms))):
        # NOTE: buffer erosion alone no longer triggers 'risk'. Just-in-time /
        # load-levelled plans legitimately finish close to the due date (thin
        # buffer) without being late, so buffer_health < buf_crit is kept only
        # as a contributing reason chip (added above) rather than a standalone
        # trigger. An order is at risk only for real slip or material issues
        # that are STILL UNRESOLVED -- a material that arrived late but has
        # since been confirmed ready (actual_ready_dt is set) is a resolved
        # historical fact, not an ongoing blocker, and stops counting here
        # even though its status correctly stays "late" for the record.
        status = "risk"

    # adherence is deliberately more sensitive than status: it uses the FULL
    # slip (including the silent-start-miss component at full weight, and
    # any delivery breach), not the confirmed-only escalation_hrs above. A
    # silent gap that never counts toward at-risk still counts here.
    adherent = (slip_hrs <= thresholds["risk_slip_hrs"]) and not delivery_breach

    # Unconfirmed / watch list: real deviation dinging adherence, but not
    # (yet, or ever, in the silent-miss case) enough to count as at-risk.
    # Deliberately excludes anything already in risk/delay/crit so the two
    # views never double-count the same order.
    unconfirmed = (status == "on") and not adherent

    return OrderStatus(
        order_pk=order.id, order_id=order.order_id, status=status, adherent=adherent,
        unconfirmed=unconfirmed, slip_hrs=slip_hrs, buffer_health=buffer_health,
        remaining_buffer=remaining_buffer, forecast_end=forecast_end, reasons=reasons)


def run_deviation_engine(db: Session, now: datetime | None = None) -> dict:
    """Recompute deviations + alerts for all orders with a current schedule.
    Preserves ack/closed status across regeneration (dedup by key)."""
    now = now or datetime.now(timezone.utc)
    thresholds = {
        "crit_slip_hrs": _thr(db, "crit_slip_hrs", 8),
        "delay_slip_hrs": _thr(db, "delay_slip_hrs", 2),
        "risk_slip_hrs": _thr(db, "risk_slip_hrs", 0.5),
        "buffer_crit_pct": _thr(db, "buffer_crit_pct", 20),
        # A silent start miss (no logged event at all) never contributes to
        # status (Orders at risk / Delayed-critical), however long it
        # persists -- it's unconfirmed, and this team would rather it sit on
        # the Unconfirmed / watch list indefinitely than eventually get
        # treated as a confirmed delay. It still fully counts toward
        # schedule adherence (see compute_order_status's adherent field).
        # The "crit" alert to the supervisor still fires immediately
        # regardless (see push_alert below) -- that's a separate, faster
        # "go check on this" signal, independent of the KPI-facing status.
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
                       f"Material late {ms.slip_days}d - {pname}",
                       "Owner: Procurement lead - cascaded into production")
        elif ms and ms.status == "risk":
            push_alert("warn", order.id, f"mat-risk-{order.order_id}",
                       f"Material at risk - {pname}",
                       f"{ms.risk_reason or 'Approaching ready date'} - Owner: Procurement lead")

        for r in comp.reasons:
            if r.kind == "time" and "Silent" in r.text:
                push_alert("crit", order.id, f"silent-{order.order_id}",
                           f"Silent start miss - {pname}", f"{r.text} - Owner: Production supervisor")
            elif r.kind == "buffer":
                push_alert("warn", order.id, f"buffer-{order.order_id}",
                           f"Buffer erosion - {pname}", f"{r.text} - Owner: Planner")
            elif r.kind == "capacity":
                push_alert("warn", order.id, f"cap-{order.order_id}",
                           f"Capacity overload - {pname}",
                           "A work center for this order is overloaded - Owner: Planner")

        if comp.status == "crit":
            push_alert("crit", order.id, f"breach-{order.order_id}",
                       f"Delivery promise at risk - {pname}",
                       f"Forecast +{comp.slip_hrs}h - buffer {comp.buffer_health}% - Owner: Supervisor + Sales")

    db.commit()
    if alerts_made:
        publish("alert_raised", {"count": alerts_made})
    return {"alerts": alerts_made, "deviations": deviations_made, "status_counts": status_counts}
