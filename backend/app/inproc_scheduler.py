"""In-process periodic scheduler for single-process deployments (e.g. Render's
free tier, where there's no separate Celery beat worker).

When PLANTRACK_SINGLE_PROCESS=1, the API process runs the deviation/material-risk
scan itself on a background daemon thread, so time-based alerts still fire without
a dedicated beat process. On a full deployment (Redis + Celery beat) this stays
off and the real beat schedule is used instead.
"""
from __future__ import annotations
import os
import threading

_thread: threading.Thread | None = None
_stop = threading.Event()


def _run_loop(interval_s: int) -> None:
    # small initial delay so the web server is serving before the first scan
    if _stop.wait(15):
        return
    while not _stop.is_set():
        try:
            # imported lazily so module import never pulls the DB engine early
            from .jobs.tasks import periodic_deviation_scan
            periodic_deviation_scan()
        except Exception:
            # a scan failure must never kill the loop or the web process
            pass
        _stop.wait(interval_s)


def start_if_enabled() -> bool:
    """Start the background scan loop iff single-process mode is enabled.
    Returns True if it started."""
    global _thread
    if os.environ.get("PLANTRACK_SINGLE_PROCESS", "0") != "1":
        return False
    if _thread is not None:
        return True
    interval = int(os.environ.get("PLANTRACK_SCAN_INTERVAL_S", "300"))
    _thread = threading.Thread(target=_run_loop, args=(interval,),
                               name="plantrack-scan", daemon=True)
    _thread.start()
    return True


def stop() -> None:
    _stop.set()