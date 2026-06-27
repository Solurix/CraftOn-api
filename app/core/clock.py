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
