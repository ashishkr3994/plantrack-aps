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
        d = self.origin.date()
        # advance over working days
        counted = 0
        while counted < full_days:
            d = d + timedelta(days=1)
            if self.is_working_day(d):
                counted += 1
        # ensure landing day is a working day
        while not self.is_working_day(d):
            d = d + timedelta(days=1)
        return self._day_start(d) + timedelta(minutes=rem)

    def working_minutes_between(self, start: datetime, end: datetime) -> int:
        """Count working minutes between two datetimes (used to place an
        order's material-ready offset relative to the schedule origin)."""
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