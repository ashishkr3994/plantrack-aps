"""Working-time calendar: convert between wall-clock datetimes and a flat
'working-minute' timeline that the CP-SAT model optimises in.

Mirrors the prototype: a working day has a fixed number of available minutes
(default 960 = two 8h shifts), Sundays are skipped, and explicit holiday dates
from the plant calendar are skipped. Operations only consume working minutes.
"""
from __future__ import annotations
from datetime import datetime, timedelta, date, time


class WorkingCalendar:
    def __init__(self, origin: datetime, minutes_per_day: int = 960,
                 holidays: set[date] | None = None, work_start_hour: int = 6):
        self.origin = origin.replace(minute=0, second=0, microsecond=0)
        self.minutes_per_day = minutes_per_day
        self.holidays = holidays or set()
        self.work_start_hour = work_start_hour

    def is_working_day(self, d: date) -> bool:
        if d.weekday() == 6:          # Sunday off
            return False
        return d not in self.holidays

    def _day_start(self, d: date) -> datetime:
        tz = self.origin.tzinfo
        return datetime.combine(d, time(self.work_start_hour), tzinfo=tz)

    def to_datetime(self, working_min: int) -> datetime:
        """Map a working-minute offset (from origin) to a wall-clock datetime,
        walking forward over working days only."""
        full_days, rem = divmod(int(working_min), self.minutes_per_day)
        # Snap to the first valid working day AT OR AFTER the origin BEFORE
        # counting full_days forward. If this snap happened only at the end
        # (after the full_days loop), an origin that itself falls on a
        # non-working day (e.g. a solve or demo reset run on a Sunday) made
        # minute 0 and minute `minutes_per_day` collapse onto the SAME
        # calendar day instead of consecutive working days -- a real bug,
        # confirmed to corrupt persisted schedules (planned_end before
        # planned_start) whenever "now" happens to fall on a Sunday.
        d = self.origin.date()
        while not self.is_working_day(d):
            d = d + timedelta(days=1)
        counted = 0
        while counted < full_days:
            d = d + timedelta(days=1)
            if self.is_working_day(d):
                counted += 1
        return self._day_start(d) + timedelta(minutes=rem)

    def working_minutes_between(self, start: datetime, end: datetime) -> int:
        """Count working minutes between two datetimes (used to place an
        order's material-ready offset relative to the schedule origin).

        This is a COARSE, whole-calendar-day approximation only -- it counts
        full working days between the two dates and ignores time-of-day
        entirely. Fine for a material-ready offset (a day-level estimate to
        begin with), but WRONG for pinning an operation to its precise
        minute: two operations on the same calendar day, hours apart, both
        collapse to the same value. Use from_datetime() below for anything
        that needs to round-trip with to_datetime() at minute precision
        (completed-operation pinning, neighbor pinning in recovery)."""
        if end <= start:
            return 0
        # simple approximation: full working days * minutes_per_day + remainder
        days = 0
        d = start.date()
        while d < end.date():
            if self.is_working_day(d):
                days += 1
            d = d + timedelta(days=1)
        return days * self.minutes_per_day

    def from_datetime(self, dt: datetime) -> int:
        """Precise inverse of to_datetime(): map a wall-clock datetime back
        to its working-minute offset from origin, at full minute precision.
        Assumes dt falls on a working day within a normal shift window (true
        for any planned operation time or logged event timestamp); a dt
        before origin's working-day start returns 0, same as to_datetime's
        own lower bound."""
        origin_day = self.origin.date()
        while not self.is_working_day(origin_day):
            origin_day = origin_day + timedelta(days=1)
        d = dt.date()
        if d < origin_day:
            return 0
        full_days = 0
        cur = origin_day
        while cur < d:
            cur = cur + timedelta(days=1)
            if self.is_working_day(cur):
                full_days += 1
        day_start = self._day_start(d)
        rem = max(0, int((dt - day_start).total_seconds() // 60))
        return full_days * self.minutes_per_day + rem
