"""Shared pause/resume pairing logic, used identically by the loader (solver
blocking windows), the deviation engine (downtime signal), and the gantt
endpoint (timeline display) -- so all three agree on how long a downtime
window actually lasted, rather than three separate implementations drifting
out of sync.

A pause event carries a MANUALLY ESTIMATED duration (downtime_mins), entered
when the outage starts and its length isn't known yet. A resume event marks
when the machine actually started running again. Once a resume exists for a
pause, its REAL elapsed time (resume_ts - pause_ts) is what actually
happened and is used instead of the estimate; the estimate remains the best
available answer only for a pause that hasn't been resumed yet.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime


@dataclass
class DowntimeWindow:
    pause_event: object            # the ActualEvent (or mapping) for the pause
    start_ts: datetime
    end_ts: datetime | None        # None if still ongoing (no resume logged yet)
    resumed: bool
    duration_mins: float           # real (resume-based) if resumed, else the estimate


def _field(ev, name):
    """Read a field from either an ORM object (attribute access, used by the
    loader and deviation engine) or a SQLAlchemy RowMapping/dict (key access,
    used by the gantt endpoint) -- this utility is shared across both."""
    try:
        return getattr(ev, name)
    except AttributeError:
        return ev[name]


def pair_pause_resume(events: list, estimate_field: str = "downtime_mins") -> list[DowntimeWindow]:
    """events: chronologically-sorted ActualEvent-like objects for ONE order
    (already filtered to that order elsewhere -- this function doesn't
    filter by order itself, only by event_type, so callers control scope).
    Pairs each pause with the next resume that follows it in the same list
    (operation_seq-aware: a resume only closes a pause on the same
    operation_seq, or an order-level pause when both are order-level)."""
    windows: list[DowntimeWindow] = []
    open_pause = None  # (event, start_ts) awaiting a resume

    def _ts(ev):
        t = _field(ev, "event_timestamp")
        return t if t.tzinfo else t.replace(tzinfo=None)

    def _matches(pause_ev, resume_ev) -> bool:
        return (_field(pause_ev, "operation_seq") or None) == (_field(resume_ev, "operation_seq") or None)

    for ev in events:
        ev_type = _field(ev, "event_type")
        if ev_type == "pause":
            # A new pause always opens a new window; if a prior one was left
            # unresumed, it stays open (still-ongoing) and this is a second,
            # independent outage -- both get returned, only the first stays
            # "ongoing" if never resumed.
            if open_pause is not None:
                p_ev, p_start = open_pause
                est = float(_field(p_ev, estimate_field) or 0)
                windows.append(DowntimeWindow(p_ev, p_start, None, False, est))
            open_pause = (ev, _ts(ev))
        elif ev_type == "resume" and open_pause is not None:
            p_ev, p_start = open_pause
            if _matches(p_ev, ev):
                real_mins = max(0.0, (_ts(ev) - p_start).total_seconds() / 60)
                windows.append(DowntimeWindow(p_ev, p_start, _ts(ev), True, real_mins))
                open_pause = None

    if open_pause is not None:
        p_ev, p_start = open_pause
        est = float(_field(p_ev, estimate_field) or 0)
        windows.append(DowntimeWindow(p_ev, p_start, None, False, est))

    return windows


def earliest_effective_start(events: list) -> "tuple[object, datetime] | None":
    """The effective 'real work began' moment for late-start purposes: the
    earliest explicit 'start' event, OR if none exists, the earliest
    'resume' event (resuming implies production is running even if a
    distinct start was never logged -- e.g. a delay before the very first
    start, resolved by a resume once work actually got underway).
    Returns (event, timestamp) or None if neither exists."""
    candidates = [e for e in events if _field(e, "event_type") in ("start", "resume")]
    if not candidates:
        return None
    first = min(candidates, key=lambda e: _field(e, "event_timestamp"))
    ts = _field(first, "event_timestamp")
    return (first, ts)
