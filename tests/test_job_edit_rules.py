"""Job edit business rules (PATCH /jobs/{id}).

Covers the four rules layered on top of owner + OPEN:
  1. edit-cutoff window (``job_edit_cutoff_hours``, Asia/Tokyo, 0 = disabled),
  2. terms lock once a worker is confirmed (notes/photos/headcount-increase only),
  3. headcount floor (never below active matchings),
  4. pending applicants get a ``job_updated`` notification on core-term changes.
"""

from __future__ import annotations

import datetime

import pytest
from fastapi.testclient import TestClient

from app.core import clock
from app.core.config import CONFIG_DEFAULTS
from tests.factories import (
    CONTRACTOR,
    WORKER,
    Member,
    apply_to_job,
    post_job,
    unique_phone,
)


def _future_date(days: int = 30) -> datetime.date:
    return clock.tokyo_today() + datetime.timedelta(days=days)


def _patch(client: TestClient, job_id: str, headers: dict[str, str], **body: object):
    return client.patch(f"/api/v1/jobs/{job_id}", json=body, headers=headers)


def _contractor(approved_member: Member) -> dict[str, str]:
    return approved_member("contractor", unique_phone(), onboard=CONTRACTOR)[0]


def _worker(approved_member: Member) -> dict[str, str]:
    return approved_member("worker", unique_phone(), onboard=WORKER)[0]


def _notification_types(client: TestClient, headers: dict[str, str]) -> list[str]:
    return [n["type"] for n in client.get("/api/v1/notifications", headers=headers).json()]


# -- rule 1: edit cutoff window ---------------------------------------------


def test_cutoff_default_registered_as_12_hours() -> None:
    assert CONFIG_DEFAULTS["job_edit_cutoff_hours"] == 12


def test_edit_allowed_well_before_start(client: TestClient, approved_member: Member) -> None:
    ch = _contractor(approved_member)
    job_id = post_job(client, ch, work_date=_future_date().isoformat())
    resp = _patch(client, job_id, ch, daily_wage=20000)
    assert resp.status_code == 200 and resp.json()["daily_wage"] == 20000


def test_edit_blocked_within_cutoff_before_start(
    client: TestClient, approved_member: Member, monkeypatch: pytest.MonkeyPatch
) -> None:
    ch = _contractor(approved_member)
    work_date = _future_date()
    job_id = post_job(client, ch, work_date=work_date.isoformat())  # starts 08:00
    start = datetime.datetime.combine(work_date, datetime.time(8, 0), tzinfo=clock.TOKYO)
    # Freeze "now" (Asia/Tokyo) to 2 h before start — inside the 12 h window.
    monkeypatch.setattr(clock, "tokyo_now", lambda: start - datetime.timedelta(hours=2))

    resp = _patch(client, job_id, ch, daily_wage=20000)
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "job_edit_window_closed"
    # The configured hours are surfaced in the localized message.
    assert "12" in resp.json()["error"]["message"]


def test_edit_blocked_after_start(client: TestClient, approved_member: Member) -> None:
    ch = _contractor(approved_member)
    yesterday = (clock.tokyo_today() - datetime.timedelta(days=1)).isoformat()
    job_id = post_job(client, ch, work_date=yesterday)
    resp = _patch(client, job_id, ch, daily_wage=20000)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "job_edit_window_closed"


def test_cutoff_zero_disables_window_check(
    client: TestClient, approved_member: Member, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Config override mechanism (env layer, same precedence chain as
    # test_config_precedence): 0 switches the window off entirely.
    monkeypatch.setenv("CRAFTON_CFG__JOB_EDIT_CUTOFF_HOURS", "0")
    ch = _contractor(approved_member)
    yesterday = (clock.tokyo_today() - datetime.timedelta(days=1)).isoformat()
    job_id = post_job(client, ch, work_date=yesterday)
    resp = _patch(client, job_id, ch, daily_wage=20000)
    assert resp.status_code == 200, resp.text


# -- rules 2 + 3: terms lock & headcount floor -------------------------------


def test_terms_locked_once_worker_confirmed(
    client: TestClient, approved_member: Member
) -> None:
    ch, wh = _contractor(approved_member), _worker(approved_member)
    # headcount 3 keeps the job OPEN (editable) after one confirmation.
    job_id = post_job(client, ch, work_date=_future_date().isoformat(), headcount=3)
    app_id = apply_to_job(client, wh, job_id)
    assert (
        client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch).status_code == 201
    )

    # Core term (wage) → locked.
    locked = _patch(client, job_id, ch, daily_wage=30000)
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "job_terms_locked"

    # Notes stay editable.
    notes = _patch(client, job_id, ch, notes="8時に現場集合")
    assert notes.status_code == 200 and notes.json()["notes"] == "8時に現場集合"

    # Headcount may increase…
    inc = _patch(client, job_id, ch, headcount=4)
    assert inc.status_code == 200 and inc.json()["headcount"] == 4

    # …but not decrease (even while still above the confirmed count).
    dec = _patch(client, job_id, ch, headcount=2)
    assert dec.status_code == 409
    assert dec.json()["error"]["code"] == "job_terms_locked"

    # Re-sending an unchanged core value is a no-op, not a violation.
    same = _patch(client, job_id, ch, daily_wage=18000)
    assert same.status_code == 200


def test_headcount_cannot_drop_below_active_matchings(
    client: TestClient, approved_member: Member
) -> None:
    ch = _contractor(approved_member)
    w1, w2 = _worker(approved_member), _worker(approved_member)
    job_id = post_job(client, ch, work_date=_future_date().isoformat(), headcount=3)
    for wh in (w1, w2):
        app_id = apply_to_job(client, wh, job_id)
        assert (
            client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch).status_code
            == 201
        )

    resp = _patch(client, job_id, ch, headcount=1)  # 2 workers hold slots
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "job_headcount_below_confirmed"


# -- rule 4: notify pending applicants on term changes ------------------------


def test_pending_applicant_notified_on_wage_change(
    client: TestClient, approved_member: Member
) -> None:
    ch, wh = _contractor(approved_member), _worker(approved_member)
    job_id = post_job(client, ch, work_date=_future_date().isoformat(), headcount=2)
    apply_to_job(client, wh, job_id)  # stays pending (not confirmed)

    assert _patch(client, job_id, ch, daily_wage=22000).status_code == 200

    notes = client.get("/api/v1/notifications", headers=wh).json()
    updated = [n for n in notes if n["type"] == "job_updated"]
    assert len(updated) == 1
    assert updated[0]["title"] and updated[0]["body"]  # localized, non-empty
    assert updated[0]["link"] == f"/jobs/{job_id}"


def test_no_notification_on_notes_only_edit(
    client: TestClient, approved_member: Member
) -> None:
    ch, wh = _contractor(approved_member), _worker(approved_member)
    job_id = post_job(client, ch, work_date=_future_date().isoformat(), headcount=2)
    apply_to_job(client, wh, job_id)

    assert _patch(client, job_id, ch, notes="持ち物: ヘルメット").status_code == 200
    assert "job_updated" not in _notification_types(client, wh)
