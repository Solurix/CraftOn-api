"""Check-in time gating (``checkin_open_minutes_before_start``, docs/07).

A worker must not be able to check in days before the shift (that let fees be
recorded before any work happened) nor after the shift has ended. The window
is Asia/Tokyo business time; ``0``/negative disables the check entirely.

The shared conftest disables the window for the other fixtures (fixed job
dates); here we re-enable it via the env config layer and freeze
``app.core.clock.tokyo_now`` like tests/test_job_edit_rules.py does.
"""

from __future__ import annotations

import datetime

import pytest
from fastapi.testclient import TestClient

from app.core import clock
from app.core.config import CONFIG_DEFAULTS
from tests.factories import Member, confirmed_matching

ENV_VAR = "CRAFTON_CFG__CHECKIN_OPEN_MINUTES_BEFORE_START"
WORK_DATE = datetime.date(2026, 8, 1)  # arbitrary fixed date; the clock is frozen


def _enable_window(monkeypatch: pytest.MonkeyPatch, minutes: int = 120) -> None:
    monkeypatch.setenv(ENV_VAR, str(minutes))


def _freeze(monkeypatch: pytest.MonkeyPatch, at: datetime.datetime) -> None:
    monkeypatch.setattr(clock, "tokyo_now", lambda: at)


def _at(hour: int, minute: int = 0, *, day_offset: int = 0) -> datetime.datetime:
    day = WORK_DATE + datetime.timedelta(days=day_offset)
    return datetime.datetime.combine(day, datetime.time(hour, minute), tzinfo=clock.TOKYO)


def _matching(client: TestClient, approved_member: Member, **job_over: object) -> tuple:
    return confirmed_matching(
        client, approved_member, work_date=WORK_DATE.isoformat(), **job_over
    )


def test_default_registered_as_120_minutes() -> None:
    assert CONFIG_DEFAULTS["checkin_open_minutes_before_start"] == 120


def test_checkin_days_early_is_rejected(
    client: TestClient, approved_member: Member, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The audited bug: check-in (and thus completion + fee) 3 days early."""
    _enable_window(monkeypatch)
    ch, wh, mid = _matching(client, approved_member)  # shift 08:00–17:00
    _freeze(monkeypatch, _at(8, 0, day_offset=-3))

    resp = client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh)
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "checkin_too_early"
    # The configured window is surfaced in the localized message.
    assert "120" in resp.json()["error"]["message"]


def test_checkin_just_inside_window_is_allowed(
    client: TestClient, approved_member: Member, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_window(monkeypatch)
    ch, wh, mid = _matching(client, approved_member)
    _freeze(monkeypatch, _at(6, 30))  # 90 min before an 08:00 start

    resp = client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "checked_in"


def test_checkin_just_outside_window_is_too_early(
    client: TestClient, approved_member: Member, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_window(monkeypatch)
    ch, wh, mid = _matching(client, approved_member)
    _freeze(monkeypatch, _at(5, 59))  # 121 min before an 08:00 start

    resp = client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "checkin_too_early"


def test_checkin_after_shift_end_is_rejected(
    client: TestClient, approved_member: Member, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_window(monkeypatch)
    ch, wh, mid = _matching(client, approved_member)  # ends 17:00
    _freeze(monkeypatch, _at(17, 1))

    resp = client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "checkin_window_closed"


def test_checkin_during_shift_is_allowed(
    client: TestClient, approved_member: Member, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_window(monkeypatch)
    ch, wh, mid = _matching(client, approved_member)
    _freeze(monkeypatch, _at(10, 0))  # mid-shift (late arrival still checks in)

    assert client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh).status_code == 200


def test_overnight_shift_end_is_next_day(
    client: TestClient, approved_member: Member, monkeypatch: pytest.MonkeyPatch
) -> None:
    """end_time <= start_time means the shift runs into the next day."""
    _enable_window(monkeypatch)
    ch, wh, mid = _matching(
        client, approved_member, start_time="22:00:00", end_time="05:00:00"
    )

    # 03:00 the next morning is still inside the shift.
    _freeze(monkeypatch, _at(3, 0, day_offset=1))
    ok = client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh)
    assert ok.status_code == 200, ok.text


def test_overnight_shift_closed_after_next_day_end(
    client: TestClient, approved_member: Member, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_window(monkeypatch)
    ch, wh, mid = _matching(
        client, approved_member, start_time="22:00:00", end_time="05:00:00"
    )

    _freeze(monkeypatch, _at(6, 0, day_offset=1))  # past the 05:00 next-day end
    resp = client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "checkin_window_closed"


def test_zero_disables_the_window(
    client: TestClient, approved_member: Member, monkeypatch: pytest.MonkeyPatch
) -> None:
    """0/negative = permissive escape hatch: any time is accepted."""
    _enable_window(monkeypatch, minutes=0)
    ch, wh, mid = _matching(client, approved_member)
    _freeze(monkeypatch, _at(8, 0, day_offset=-3))  # would be far too early

    assert client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh).status_code == 200


def test_completion_stays_status_gated_behind_checkin(
    client: TestClient, approved_member: Member, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With check-in gated, premature completion is impossible: the completion
    endpoints stay status-gated only (no separate time check needed)."""
    _enable_window(monkeypatch)
    ch, wh, mid = _matching(client, approved_member)
    _freeze(monkeypatch, _at(8, 0, day_offset=-3))

    # Too early to check in → completion request is refused by status.
    assert client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh).status_code == 409
    cr = client.post(f"/api/v1/matchings/{mid}/complete-request", headers=wh)
    assert cr.status_code == 409
    assert cr.json()["error"]["code"] == "not_checked_in"
    ap = client.post(f"/api/v1/matchings/{mid}/approve-completion", headers=ch)
    assert ap.status_code == 409
    assert ap.json()["error"]["code"] == "completion_not_requested"

    # Inside the window the normal happy path proceeds and records the fee.
    _freeze(monkeypatch, _at(8, 30))
    assert client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh).status_code == 200
    assert client.post(f"/api/v1/matchings/{mid}/complete-request", headers=wh).status_code == 200
    done = client.post(f"/api/v1/matchings/{mid}/approve-completion", headers=ch)
    assert done.status_code == 200
    assert done.json()["status"] == "completed"
    assert done.json()["fee_status"] == "unpaid"
