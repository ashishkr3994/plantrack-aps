"""Async scheduling task. Kicks off a CP-SAT solve, time-boxed, and persists the
result. Updates the solve_job row through its lifecycle so the API can poll.
"""
from datetime import datetime, timezone

from .celery_app import celery_app
from ..database import SessionLocal
from .. import models
from ..engine.loader import load_scheduling_input
from ..engine.cpsat_engine import solve as cpsat_solve
from ..engine.writer import persist
from ..events_bus import publish


def _now():
    return datetime.now(timezone.utc)


@celery_app.task(name="plantrack.solve_schedule")
def solve_schedule(job_id: str, mode: str = "forward", time_budget_s: int = 30,
                   order_ids=None, leveling: str = "off"):
    db = SessionLocal()
    try:
        job = db.query(models.SolveJob).filter_by(job_id=job_id).first()
        if job:
            job.status = "running"
            job.started_at = _now()
            db.commit()

        si = load_scheduling_input(db, order_ids=order_ids)
        result = cpsat_solve(si, max_seconds=time_budget_s, leveling=leveling)

        summary = {
            "status": result.status,
            "feasible": result.feasible,
            "makespan": result.makespan,
            "weighted_tardiness": result.weighted_tardiness,
            "wall_time_s": result.wall_time_s,
            "orders_total": len(result.orders),
            "orders_on_time": sum(1 for o in result.orders if o.on_time),
            "bottleneck_machine": result.explain.get("bottleneck_machine"),
            "machine_load_min": result.explain.get("machine_load_min", {}),
            "late_orders": [
                {"order_id": o.order_id, "reason": o.bottleneck}
                for o in result.orders if not o.on_time
            ],
        }

        if result.feasible:
            persist(db, si, result, mode=mode)

        job = db.query(models.SolveJob).filter_by(job_id=job_id).first()
        if job:
            job.status = "succeeded" if result.feasible else "failed"
            job.result = summary
            job.error = None if result.feasible else f"solver returned {result.status}"
            job.finished_at = _now()
            db.commit()
        if result.feasible:
            publish("schedule_updated", {"job_id": job_id,
                    "orders_on_time": summary["orders_on_time"],
                    "orders_total": summary["orders_total"]})
        return summary
    except Exception as e:  # noqa: BLE001
        db.rollback()
        job = db.query(models.SolveJob).filter_by(job_id=job_id).first()
        if job:
            job.status = "failed"
            job.error = str(e)
            job.finished_at = _now()
            db.commit()
        raise
    finally:
        db.close()


@celery_app.task(name="plantrack.periodic_deviation_scan")
def periodic_deviation_scan():
    """Periodic: recompute material risk + capacity + deviations so time-based
    signals (silent start miss, approaching material-ready) surface on their own,
    even when nobody triggers a solve. Scheduled via Celery beat."""
    from ..engine.material_init import ensure_material_status
    from ..engine.material_risk import evaluate_material_risk
    from ..engine.capacity import compute_capacity_load
    from ..engine.deviation import run_deviation_engine
    db = SessionLocal()
    try:
        ensure_material_status(db)
        evaluate_material_risk(db)
        compute_capacity_load(db)
        result = run_deviation_engine(db)
        return result
    finally:
        db.close()
