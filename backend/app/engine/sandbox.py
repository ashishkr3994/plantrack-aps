"""What-if sandbox: solve against a COPY of the live plan with overrides,
without persisting anything to the live schedule.

A planner adds orders to a scenario (all of them, unmodified, by default), then
optionally overrides a few: new/partial quantity, priority, a new due date, a
hypothetical execution event (downtime, scrap, or an early completion), or
excludes the order from the scenario entirely. We load the real scheduling
input, apply everything in memory, run the CP-SAT engine, and return a full
live-vs-what-if comparison: KPIs, per-order quantity/priority/committed
date/planned delivery/buffer, a stage-by-stage schedule (material ready, each
routing operation, production end, dispatch, delivery), and -- for the what-if
side -- a risk signal and any hypothetical execution events applied. Nothing is
written to planned_schedule, actual_event, or any other table.

Honest scope notes (documented rather than silently approximated):
  * KPI classification here is derived directly from each solve's own
    lateness/buffer numbers, using the SAME threshold VALUES as the live
    dashboard's deviation engine (crit/delay/risk slip hours). It is NOT the
    live deviation engine itself, which scores actual logged execution against
    a baseline -- a hypothetical scenario has no execution history to score.
  * material_at_risk reports the same figure on both live and what-if sides,
    because a sandbox solve never touches material readiness data.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import text

from .loader import load_scheduling_input, PACK_DAYS, DISPATCH_DAYS, TRANSPORT_DAYS
from .cpsat_engine import solve as cpsat_solve
from .deviation import _thr
from .kpi import compute_kpis

DEFAULT_AVAILABLE_MIN = 600  # single plant, one 10h shift -- mirrors capacity.py


@dataclass
class EventOverride:
    """A hypothetical execution event to test in the scenario -- never logged
    to actual_event. event_timestamp defaults to now if omitted."""
    event_type: str                        # "pause" | "scrap" | "complete"
    operation_seq: int
    event_timestamp: str | None = None     # ISO; used by pause/complete
    downtime_mins: int = 0                 # pause
    whole_wc: bool = False                 # pause: block the whole machine, not just this order
    qty: int = 0                           # scrap: units to rework


@dataclass
class OrderOverride:
    order_id: str                  # business id
    qty: int | None = None
    priority: str | None = None
    committed_due_dt: str | None = None   # ISO date
    exclude: bool = False
    partial_qty: int | None = None        # reschedule only part of the order
    events: list[EventOverride] = field(default_factory=list)


@dataclass
class SandboxRequest:
    overrides: list[OrderOverride] = field(default_factory=list)
    mode: str = "forward"
    time_budget_s: int = 15
    overtime_hrs_per_day: int = 0          # extra working hours/day (plan lever)
    leveling: str = "off"                  # 'off' | 'soft' | 'strict' -- what-if side only


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _thresholds(db: Session) -> dict:
    return {
        "crit_slip_hrs": _thr(db, "crit_slip_hrs", 8),
        "delay_slip_hrs": _thr(db, "delay_slip_hrs", 2),
        "risk_slip_hrs": _thr(db, "risk_slip_hrs", 0.5),
    }


def _classify(lateness_min: float, buffer_hrs: float | None, thresholds: dict) -> str:
    """Same bucket names/threshold values as the live dashboard's deviation
    engine (on/risk/delay/crit), computed directly from a solve result's own
    lateness and buffer rather than logged execution deviation."""
    lateness_hrs = max(0.0, lateness_min) / 60
    if lateness_hrs >= thresholds["crit_slip_hrs"]:
        return "crit"
    if lateness_hrs >= thresholds["delay_slip_hrs"]:
        return "delay"
    if lateness_hrs >= thresholds["risk_slip_hrs"] or (buffer_hrs is not None and buffer_hrs < 24):
        return "risk"
    return "on"


def _available_min(db: Session) -> int:
    avail = db.execute(text(
        "SELECT COALESCE(SUM(available_min),0) FROM plant_calendar WHERE NOT is_holiday")).scalar()
    return int(avail) if avail and int(avail) > 0 else DEFAULT_AVAILABLE_MIN


def _material_at_risk(db: Session) -> int:
    return db.execute(text(
        "SELECT count(*) FROM material_status WHERE status IN ('late','risk')")).scalar() or 0


def _capacity_conflicts(res, cal, available_min: int) -> int:
    """Bucket every operation by (work centre, calendar day) and count days
    where scheduled demand exceeds available minutes -- same definition as
    capacity.py's overloaded-day count, computed here purely in memory."""
    demand: dict[tuple, int] = {}
    for op in res.operations:
        d = cal.to_datetime(op.start_min).date()
        key = (op.work_center, d)
        demand[key] = demand.get(key, 0) + (op.end_min - op.start_min)
    return sum(1 for v in demand.values() if v > available_min)


def _milestones(order_input, res, cal):
    """Full stage-by-stage chain for one order: material ready, each routing
    operation in sequence (parallel ops as separate rows sharing a start),
    production end, dispatch, delivery. Uses the SAME pack/dispatch/delivery
    formula the writer applies when persisting a real schedule, so these dates
    match what would actually be written if this scenario were applied."""
    ops = [op for op in res.operations if op.order_id == order_input.order_id]
    ops.sort(key=lambda x: x.operation_seq)
    stages = [{
        "stage": "Material ready", "kind": "milestone",
        "start": _iso(cal.to_datetime(order_input.material_ready_min)), "end": None,
    }]
    for op in ops:
        stages.append({
            "stage": op.work_center, "kind": "op", "operation_seq": op.operation_seq,
            "parallel_group": op.parallel_group,
            "start": _iso(cal.to_datetime(op.start_min)),
            "end": _iso(cal.to_datetime(op.end_min)),
            # true processing time (working-minutes) -- see run_sandbox
            # docstring for why (end - start) alone is unreliable across a
            # shift/day boundary.
            "duration_min": op.duration_min,
        })
    prod_end = delivery = None
    if ops:
        prod_end_min = max(op.end_min for op in ops)
        prod_end = cal.to_datetime(prod_end_min)
        lead = int(getattr(order_input, "delivery_lead_days", PACK_DAYS + DISPATCH_DAYS + TRANSPORT_DAYS))
        pack = prod_end + timedelta(days=min(PACK_DAYS, lead))
        dispatch = pack + timedelta(days=min(DISPATCH_DAYS, max(0, lead - PACK_DAYS)))
        delivery = prod_end + timedelta(days=lead)
        stages.append({"stage": "Production end", "kind": "milestone", "start": None, "end": _iso(prod_end)})
        stages.append({"stage": "Dispatch", "kind": "milestone", "start": _iso(prod_end), "end": _iso(dispatch)})
        stages.append({"stage": "Delivery", "kind": "milestone", "start": None, "end": _iso(delivery)})
    return stages, prod_end, delivery


def _live_downtime(db: Session) -> list[dict]:
    """Logged downtime affecting the current live schedule -- same query as
    /schedule/gantt, kept here so the sandbox's live timeline panel matches
    the real Timeline screen exactly."""
    rows = db.execute(text("""
        SELECT ae.event_timestamp, ae.downtime_mins, ae.downtime_reason,
               o.order_id, oo.work_center
        FROM actual_event ae
        LEFT JOIN order_header o ON o.id = ae.order_id
        LEFT JOIN order_operation oo ON oo.order_id = ae.order_id
            AND oo.operation_seq = ae.operation_seq
            AND oo.schedule_id = (
                SELECT ps2.id FROM planned_schedule ps2
                WHERE ps2.order_id = ae.order_id AND ps2.is_current
                LIMIT 1
            )
        WHERE ae.event_type = 'pause' AND ae.downtime_mins > 0
        ORDER BY ae.event_timestamp
    """)).mappings().all()
    out = []
    for d in rows:
        reason = d["downtime_reason"] or ""
        out.append({
            "work_center": d["work_center"], "whole_wc": reason.startswith("[WC]"),
            "order_id": d["order_id"], "start": _iso(d["event_timestamp"]),
            "duration_mins": d["downtime_mins"], "reason": reason,
        })
    return out


def _live_snapshot(db: Session) -> dict:
    """Every order's CURRENT persisted state, read directly from the database
    -- never re-solved. This is the fix for a real bug: re-solving for 'live'
    used the solver's default leveling ('off', pure earliest-finish), which
    can differ substantially from whatever leveling mode (or recovery action)
    actually produced the schedule on the real Dashboard. Reading the persisted
    row is the only way to guarantee 'live' truly matches what's live."""
    rows = db.execute(text("""
        SELECT o.id AS pk, o.order_id, o.order_qty, o.priority, o.customer,
               o.committed_delivery_date,
               ps.id AS sched_pk, ps.planned_material_ready_dt,
               ps.planned_prod_end_dt, ps.planned_dispatch_dt,
               ps.planned_delivery_dt, ps.buffer_hrs
        FROM order_header o
        LEFT JOIN planned_schedule ps ON ps.order_id = o.id AND ps.is_current
    """)).mappings().all()
    return {r["order_id"]: dict(r) for r in rows}


def _live_ops(db: Session, pk: int | None, sched_pk: int | None):
    if pk is None or sched_pk is None:
        return []
    return db.execute(text("""
        SELECT operation_seq, work_center, parallel_group, planned_start, planned_end, duration_mins
        FROM order_operation WHERE order_id = :pk AND schedule_id = :sid
        ORDER BY operation_seq
    """), {"pk": pk, "sid": sched_pk}).mappings().all()


def _live_stages(row: dict, ops) -> list[dict]:
    """Stage-by-stage chain built entirely from persisted columns/rows --
    same shape as _milestones, so the frontend renders both sides identically."""
    if row.get("sched_pk") is None:
        return []
    stages = [{
        "stage": "Material ready", "kind": "milestone",
        "start": _iso(row["planned_material_ready_dt"]), "end": None,
    }]
    for op in ops:
        stages.append({
            "stage": op["work_center"], "kind": "op", "operation_seq": op["operation_seq"],
            "parallel_group": op["parallel_group"],
            "start": _iso(op["planned_start"]), "end": _iso(op["planned_end"]),
            # true processing time (working-minutes), stored independently of
            # the wall-clock start/end -- see run_sandbox docstring for why
            # (end - start) alone is unreliable across a shift/day boundary.
            "duration_min": float(op["duration_mins"]) if op["duration_mins"] is not None else None,
        })
    if row.get("planned_prod_end_dt"):
        stages.append({"stage": "Production end", "kind": "milestone", "start": None,
                       "end": _iso(row["planned_prod_end_dt"])})
        stages.append({"stage": "Dispatch", "kind": "milestone",
                       "start": _iso(row["planned_prod_end_dt"]), "end": _iso(row["planned_dispatch_dt"])})
        stages.append({"stage": "Delivery", "kind": "milestone", "start": None,
                       "end": _iso(row["planned_delivery_dt"])})
    return stages


def _date_differs(a, b) -> bool:
    if a is None and b is None:
        return False
    if (a is None) != (b is None):
        return True
    return a.date() != b.date()


def _last_solve_leveling(db: Session) -> str | None:
    """Best-effort: the leveling mode used in the most recent full solve, read
    from the audit log (no dedicated column persists this on planned_schedule
    itself). This reflects the last FULL solve specifically -- if a single
    order was since adjusted by a targeted recovery, that order's schedule may
    not trace to this mode, so it's labelled as a best-effort indicator, not a
    per-order guarantee."""
    row = db.execute(text("""
        SELECT detail->>'leveling' FROM audit_log
        WHERE action = 'solve' AND entity_type = 'schedule'
        ORDER BY at DESC LIMIT 1
    """)).scalar()
    return row


def run_sandbox(db: Session, req: SandboxRequest) -> dict:
    thresholds = _thresholds(db)
    available_min = _available_min(db)
    material_at_risk = _material_at_risk(db)  # same both sides -- see module docstring

    # ---- live: read the ACTUAL persisted schedule directly. Never re-solved,
    # so it always matches the real Dashboard/Orders/Timeline exactly, however
    # it was produced (any leveling mode, a partial recovery, pinned orders). ----
    live = _live_snapshot(db)
    downtime_live = _live_downtime(db)
    kpis_live = compute_kpis(db)   # same computation the real Dashboard uses

    # ---- scenario: fresh load, apply overrides + levers ----
    # baseline shift length MUST match the real solve's own default (600 min,
    # a 10h shift -- see load_scheduling_input's default) or every comparison
    # here silently runs on a different working day than the real shop. This
    # was a real, confirmed bug: hardcoding a different baseline made every
    # what-if scenario simulate a longer shift than reality regardless of the
    # overtime lever, making what-if durations look artificially shorter than
    # live purely from a shift-length mismatch, not from any real difference.
    minutes_per_day = 600 + max(0, int(req.overtime_hrs_per_day)) * 60
    si = load_scheduling_input(db, minutes_per_day=minutes_per_day)
    cal = si.calendar
    overrides = {ov.order_id: ov for ov in req.overrides}

    kept = []
    applied = []   # human-readable record of what the scenario changed
    extra_downtime: list[tuple] = []
    downtime_whatif: list[dict] = []   # Gantt-friendly, for the timeline comparison
    for o in si.orders:
        ov = overrides.get(o.order_id)
        if ov and ov.exclude:
            applied.append(f"{o.order_id}: excluded")
            continue
        if ov:
            if ov.partial_qty is not None and ov.partial_qty > 0:
                o.qty = ov.partial_qty
                applied.append(f"{o.order_id}: partial qty {ov.partial_qty}")
            elif ov.qty is not None and ov.qty > 0:
                o.qty = ov.qty
                applied.append(f"{o.order_id}: qty -> {ov.qty}")
            if ov.priority in ("HIGH", "MED", "LOW"):
                o.priority = ov.priority
                applied.append(f"{o.order_id}: priority -> {ov.priority}")
            if ov.committed_due_dt:
                try:
                    due = datetime.fromisoformat(ov.committed_due_dt)
                    if due.tzinfo is None:
                        due = due.replace(tzinfo=timezone.utc)
                    o.committed_due_dt = due
                    o.committed_due_min = max(0, cal.working_minutes_between(si.origin, due))
                    applied.append(f"{o.order_id}: due -> {due.date().isoformat()}")
                except ValueError:
                    pass
            for ev in ov.events:
                ts = ev.event_timestamp
                dt = datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if ev.event_type == "scrap" and ev.qty > 0:
                    o.rework_units += ev.qty
                    applied.append(f"{o.order_id}: scrap +{ev.qty} units (rework)")
                elif ev.event_type == "complete" and ev.operation_seq is not None:
                    end_min = max(0, cal.working_minutes_between(si.origin, dt))
                    o.completed_ops[ev.operation_seq] = end_min
                    applied.append(f"{o.order_id}: op {ev.operation_seq} marked complete")
                elif ev.event_type == "pause" and ev.downtime_mins > 0:
                    start_min = max(0, cal.working_minutes_between(si.origin, dt))
                    end_min = start_min + ev.downtime_mins
                    wc = next((op.work_center for op in o.ops if op.seq == ev.operation_seq), None)
                    extra_downtime.append((wc, start_min, end_min, None if ev.whole_wc else o.pk))
                    downtime_whatif.append({
                        "work_center": wc, "whole_wc": ev.whole_wc, "order_id": o.order_id,
                        "start": _iso(cal.to_datetime(start_min)), "duration_mins": ev.downtime_mins,
                        "reason": (f"[WC] hypothetical downtime" if ev.whole_wc else "hypothetical downtime"),
                    })
                    scope = "whole machine" if ev.whole_wc else "this order only"
                    applied.append(f"{o.order_id}: downtime {ev.downtime_mins}min on {wc} ({scope})")
        kept.append(o)
    si.orders = kept
    si.downtime_blocks = list(si.downtime_blocks) + extra_downtime
    if req.overtime_hrs_per_day:
        applied.append(f"overtime: +{req.overtime_hrs_per_day}h/day")

    scenario = cpsat_solve(si, max_seconds=req.time_budget_s, leveling=req.leveling)

    if not scenario.feasible:
        return {
            "feasible": False,
            "mode": req.mode,
            "status": scenario.status,
            "message": ("This scenario has no feasible schedule with these overrides -- "
                       "try relaxing a due date, quantity, or excluding an order."),
            "applied_changes": applied,
        }

    # ---- KPIs for the what-if side, computed in memory (nothing persisted) ----
    def kpis_for_whatif(res, cal_):
        buckets = {"on": 0, "risk": 0, "delay": 0, "crit": 0}
        for o in res.orders:
            buckets[_classify(o.lateness_min, None, thresholds)] += 1
        total = len(res.orders)
        on_track = buckets["on"]
        at_risk = buckets["risk"] + buckets["delay"] + buckets["crit"]
        delayed_critical = buckets["delay"] + buckets["crit"]
        adherence_pct = round(100.0 * on_track / total) if total else None
        otd_count = sum(1 for o in res.orders if o.on_time)
        otd_pct = round(100.0 * otd_count / total) if total else None
        return {
            "orders": total,
            "schedule_adherence_pct": adherence_pct,
            "on_time_delivery_pct": otd_pct,
            "orders_at_risk": at_risk,
            "delayed_critical": delayed_critical,
            "material_at_risk": material_at_risk,
            "capacity_conflicts": _capacity_conflicts(res, cal_, available_min),
        }

    kpis_whatif = kpis_for_whatif(scenario, cal)

    # ---- per-order comparison ----
    scen_input_by_id = {o.order_id: o for o in si.orders}

    orders_out = []
    for o in scenario.orders:
        scen_in = scen_input_by_id.get(o.order_id)
        if scen_in is None:
            continue
        live_row = live.get(o.order_id, {})
        live_ops = _live_ops(db, live_row.get("pk"), live_row.get("sched_pk"))
        stages_live = _live_stages(live_row, live_ops)
        stages_whatif, _pe_whatif, delivery_whatif = _milestones(scen_in, scenario, cal)

        buffer_live_hrs = (float(live_row["buffer_hrs"])
                          if live_row.get("buffer_hrs") is not None else None)
        buffer_whatif_hrs = (
            (scen_in.committed_due_dt - delivery_whatif).total_seconds() / 3600
            if delivery_whatif else None)

        status_whatif = _classify(o.lateness_min, buffer_whatif_hrs, thresholds)
        risk_signal_whatif = o.bottleneck if status_whatif != "on" else None

        ov = overrides.get(o.order_id)
        committed_live_date = live_row.get("committed_delivery_date")
        changed = bool(
            (live_row.get("order_qty") != scen_in.qty)
            or (live_row.get("priority") != scen_in.priority)
            or (committed_live_date is not None
                and committed_live_date.isoformat() != scen_in.committed_due_dt.date().isoformat())
            or _date_differs(live_row.get("planned_delivery_dt"), delivery_whatif)
            or (buffer_live_hrs is not None and buffer_whatif_hrs is not None
                and round(buffer_live_hrs) != round(buffer_whatif_hrs))
            or bool(ov and ov.events)
        )

        orders_out.append({
            "order_id": o.order_id,
            "customer": live_row.get("customer"),
            "qty_live": live_row.get("order_qty"),
            "qty_whatif": scen_in.qty,
            "priority_live": live_row.get("priority"),
            "priority_whatif": scen_in.priority,
            "committed_live": committed_live_date.isoformat() if committed_live_date else None,
            "committed_whatif": scen_in.committed_due_dt.date().isoformat(),
            "planned_delivery_live": _iso(live_row.get("planned_delivery_dt")),
            "planned_delivery_whatif": _iso(delivery_whatif),
            "buffer_hrs_live": round(buffer_live_hrs, 1) if buffer_live_hrs is not None else None,
            "buffer_hrs_whatif": round(buffer_whatif_hrs, 1) if buffer_whatif_hrs is not None else None,
            "status_whatif": status_whatif,
            "risk_signal_whatif": risk_signal_whatif,
            "schedule_live": stages_live,
            "schedule_whatif": stages_whatif,
            "execution_events_whatif": [
                {"event_type": ev.event_type, "operation_seq": ev.operation_seq,
                 "downtime_mins": ev.downtime_mins, "whole_wc": ev.whole_wc, "qty": ev.qty}
                for ev in (ov.events if ov else [])
            ],
            "changed": changed,
        })

    return {
        "feasible": True,
        "mode": req.mode,
        "leveling_live": _last_solve_leveling(db),
        "leveling_whatif": req.leveling,
        "kpis_live": kpis_live,
        "kpis_whatif": kpis_whatif,
        "orders": sorted(orders_out, key=lambda d: d["order_id"]),
        "downtime_live": downtime_live,
        "downtime_whatif": downtime_whatif,
        "applied_changes": applied,
        "note": ("Sandbox only - the live schedule was not modified. 'Live' figures are "
                "read directly from the current persisted schedule (never re-solved), so "
                "they always match the real Dashboard. Material-at-risk is unaffected by "
                "scenario overrides, so it reports the live figure on both sides. "
                "'Live leveling' reflects the most recent full solve -- if a single order "
                "was since adjusted by a targeted recovery, that order may not trace to it."),
        "baseline_order_count": len(live),
    }
