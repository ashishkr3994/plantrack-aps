"""Compute per-work-center daily capacity load from the current scheduled
operations, and flag overloaded cells. Populates capacity_load (which the
Capacity screen and the deviation engine's capacity signal both read).

Demand for a day = the actual working minutes of every operation that overlap
that day's shift window(s), prorated across every calendar day the operation
spans -- NOT the operation's whole duration dumped onto the single day its
planned_start happens to fall on. An operation that runs from Tuesday evening
into Wednesday morning genuinely occupies part of both days.

The "which orders overlap this day" drill-down (capacity_cell() in
routers/dashboard.py) uses the same per-day proration via
operation_minutes_on_day() below, so its per-operation numbers always sum to
exactly this module's aggregate for that cell -- an operation's FULL duration
(which may span several days) is not what's shown there; only its actual
portion of that one specific day is.

Available minutes come from the plant calendar (sum of shift available_min
on working days), defaulting to 600 (one 10h shift).
"""
from __future__ import annotations
from datetime import datetime, timezone, date, time, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import text

from .. import models

DEFAULT_AVAILABLE_MIN = 600  # single plant, one 10h shift


def load_shift_config(db: Session) -> tuple[int, list[tuple], set]:
    """Shared by compute_capacity_load and the capacity_cell drill-down, so
    both agree on what a 'working day' and a 'shift window' are -- the exact
    same definition the solver's calendar.py uses (Sunday off, plus explicit
    holiday_date rows; days_active isn't consulted since the solver doesn't
    consult it either). Returns (available_min_per_day, shift_windows, holidays)."""
    shifts = db.execute(text(
        "SELECT start_time, end_time, available_min FROM plant_calendar WHERE NOT is_holiday"
    )).fetchall()
    available_min = sum(int(s.available_min or 0) for s in shifts) or DEFAULT_AVAILABLE_MIN
    shift_windows = [(s.start_time, s.end_time) for s in shifts if s.start_time and s.end_time]
    if not shift_windows:
        shift_windows = [(time(6, 0), time(22, 0))]  # fallback: matches DEFAULT_AVAILABLE_MIN's span
    holidays = {
        row.holiday_date for row in db.execute(text(
            "SELECT holiday_date FROM plant_calendar WHERE is_holiday AND holiday_date IS NOT NULL"
        )).fetchall()
    }
    return available_min, shift_windows, holidays


def is_working_day(d: date, holidays: set) -> bool:
    return d.weekday() != 6 and d not in holidays  # Sunday off, matches calendar.py


def operation_minutes_on_day(p_start: datetime, p_end: datetime, d: date,
                             shift_windows: list[tuple]) -> float:
    """How many of THIS operation's minutes actually fall within THIS one
    calendar day's shift window(s) -- the same overlap calculation
    compute_capacity_load uses per day, exposed here so a drill-down can
    show each operation's real portion of a specific day instead of its
    full, total duration (which may span several days and always sums to
    more than what any single day actually shows)."""
    total = 0.0
    for shift_start, shift_end in shift_windows:
        win_start = datetime.combine(d, shift_start, tzinfo=p_start.tzinfo)
        win_end = datetime.combine(d, shift_end, tzinfo=p_start.tzinfo)
        overlap = min(p_end, win_end) - max(p_start, win_start)
        total += max(0.0, overlap.total_seconds() / 60)
    return total


def compute_capacity_load(db: Session) -> dict:
    """Recompute capacity_load from order_operation rows. Returns a summary."""
    available_min, shift_windows, holidays = load_shift_config(db)

    ops = db.execute(text("""
        SELECT oo.work_center, oo.planned_start, oo.planned_end
        FROM order_operation oo
        JOIN planned_schedule ps ON ps.id = oo.schedule_id AND ps.is_current
        WHERE oo.planned_start IS NOT NULL AND oo.planned_end IS NOT NULL
    """)).fetchall()

    # accumulate prorated minutes per (work_center, day)
    demand: dict[tuple[str, date], float] = {}
    for wc, p_start, p_end in ops:
        if p_end <= p_start:
            continue
        d = p_start.date()
        while d <= p_end.date():
            if is_working_day(d, holidays):
                minutes = operation_minutes_on_day(p_start, p_end, d, shift_windows)
                if minutes > 0:
                    key = (wc, d)
                    demand[key] = demand.get(key, 0.0) + minutes
            d += timedelta(days=1)

    db.execute(text("DELETE FROM capacity_load"))
    now = datetime.now(timezone.utc)
    overloaded = 0
    # "Overloaded" used to mean demand > available_min, i.e. more than 100%.
    # That's the right test for a multi-capacity (cumulative) work centre,
    # where genuine over-100% demand is possible. But for a single-capacity,
    # no-overlap work centre -- every work centre in this shop today -- the
    # solver physically cannot double-book it, so prorated demand can never
    # exceed available_min; the day tops out at exactly 100%. Under a strict
    # ">" test, a machine running fully booked for weeks straight (the
    # textbook definition of a bottleneck) would never once show as
    # overloaded. >=99% catches "no meaningful slack left" for a
    # fully-packed single-capacity day, while still catching genuine >100%
    # overage on a multi-capacity work centre if one is ever configured.
    OVERLOAD_THRESHOLD = 0.99
    for (wc, d), total_min in demand.items():
        load_pct = round(total_min / available_min * 100, 2) if available_min else 0
        is_over = total_min >= available_min * OVERLOAD_THRESHOLD
        if is_over:
            overloaded += 1
        db.add(models.CapacityLoad(
            work_center=wc, load_date=d, available_min=available_min,
            demand_min=total_min, load_pct=load_pct, overloaded=is_over, computed_at=now))
    db.commit()
    return {"cells": len(demand), "overloaded": overloaded, "available_min_per_day": available_min}


def bottleneck_recommendations(db: Session, min_overloaded_days: int = 2) -> list[dict]:
    """Identify structurally-overloaded work centres and recommend adding
    capacity (e.g. a second station). Analysis only -- no schedule change.

    A work centre is flagged when it is overloaded on >= min_overloaded_days
    distinct days, since a one-off spike isn't a structural bottleneck. For each,
    we report how many days it's overloaded and its peak load, and phrase a
    recommendation a planner can act on.
    """
    rows = db.execute(text("""
        SELECT work_center,
               COUNT(*) FILTER (WHERE overloaded)          AS over_days,
               COUNT(*)                                     AS total_days,
               COALESCE(MAX(load_pct), 0)                   AS peak_load_pct,
               COALESCE(AVG(load_pct) FILTER (WHERE overloaded), 0) AS avg_over_pct
        FROM capacity_load
        GROUP BY work_center
        HAVING COUNT(*) FILTER (WHERE overloaded) >= :mind
        ORDER BY over_days DESC, peak_load_pct DESC
    """), {"mind": min_overloaded_days}).fetchall()

    recs = []
    for wc, over_days, total_days, peak, avg_over in rows:
        recs.append({
            "work_center": wc,
            "overloaded_days": int(over_days),
            "total_days": int(total_days),
            "peak_load_pct": round(float(peak), 1),
            "avg_overload_pct": round(float(avg_over), 1),
            "recommendation": (
                f"{wc} is a bottleneck - overloaded on {int(over_days)} "
                f"day(s), peaking at {round(float(peak))}% of capacity. "
                f"Adding a second {wc} station (or a parallel resource) would "
                f"relieve this constraint and reduce capacity conflicts."),
        })
    return recs   
