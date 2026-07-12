"""Time helpers. Store UTC; evaluate business rules in Asia/Tokyo (docs/CLAUDE.md).

Centralized so tests can monkeypatch a fixed "today"/"now" deterministically.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

TOKYO = ZoneInfo("Asia/Tokyo")
UTC = datetime.UTC


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(tz=UTC)


def tokyo_now() -> datetime.datetime:
    return datetime.datetime.now(tz=TOKYO)


def tokyo_today() -> datetime.date:
    """Current calendar date in Asia/Tokyo (visa-expiry comparisons use this)."""
    return tokyo_now().date()


def combine_tokyo(day: datetime.date, time_of_day: datetime.time) -> datetime.datetime:
    """A business date + time-of-day (e.g. a job's ``work_date`` + ``start_time``)
    interpreted in Asia/Tokyo — the timezone all business rules run in."""
    return datetime.datetime.combine(day, time_of_day, tzinfo=TOKYO)
