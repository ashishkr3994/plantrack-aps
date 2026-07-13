"""Compute per-work-center daily capacity load from the current scheduled
operations, and flag overloaded cells. Populates capacity_load (which the
Capacity screen and the deviation engine's capacity signal both read).

Demand for a day = sum of operation durations whose planned window falls on that
day (simple day-bucketing by planned_start). Available minutes come from the
plant calendar (sum of shift available_min), defaulting to 960 (two 8h shifts).
"""
from __future__ import annotations
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import text

from .. import models

DEFAULT_AVAILABLE_MIN = 600  # single plant, one 10h shift


def compute_capacity_load(db: Session) -> dict:
    """Recompute capacity_load from order_operation rows. Returns a summary."""
    # available minutes per day: total across active shifts (single plant model)
    avail = db.execute(text(
        "SELECT COALESCE(SUM(available_min),0) FROM plant_calendar WHERE NOT is_holiday")).scalar()
    available_min = int(avail) if avail and int(avail) > 0 else DEFAULT_AVAILABLE_MIN

    # demand per (work_center, day) from scheduled operations
    rows = db.execute(text("""
        SELECT work_center,
               (planned_start AT TIME ZONE 'UTC')::date AS d,
               COALESCE(SUM(duration_mins), 0) AS demand
        FROM order_operation
        WHERE planned_start IS NOT NULL
        GROUP BY work_center, (planned_start AT TIME ZONE 'UTC')::date
    """)).fetchall()

    db.execute(text("DELETE FROM capacity_load"))
    now = datetime.now(timezone.utc)
    overloaded = 0
    for wc, d, demand in rows:
        demand = float(demand or 0)
        load_pct = round(demand / available_min * 100, 2) if available_min else 0
        is_over = demand > available_min
        if is_over:
            overloaded += 1
        db.add(models.CapacityLoad(
            work_center=wc, load_date=d, available_min=available_min,
            demand_min=demand, load_pct=load_pct, overloaded=is_over, computed_at=now))
    db.commit()
    return {"cells": len(rows), "overloaded": overloaded, "available_min_per_day": available_min}


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
               COUNT(*) FILTER (WHERE overloaded)          AS over_days,
               COUNT(*)                                     AS total_days,
               COALESCE(MAX(load_pct), 0)                   AS peak_load_pct,
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
