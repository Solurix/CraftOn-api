"""Chat endpoint: server-side masking is authoritative, plus participant authZ."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

Member = Callable[..., tuple[dict[str, str], str]]

_CONTRACTOR = {"company_name": "ABC", "contact_person": "S", "prefecture": "Tokyo"}
_WORKER = {"nationality": "JP", "worker_class": "employee", "trades": ["大工"]}
_JOB = {
    "trades": ["大工"], "work_date": "2026-07-01",
    "start_time": "08:00:00", "end_time": "17:00:00",
    "prefecture": "Tokyo", "daily_wage": 18000, "headcount": 1,
}

_phone = iter(f"+8190560{i:05d}" for i in range(1, 99999))


def _confirmed_matching(client: TestClient, approved_member: Member) -> tuple[dict, dict, str]:
    ch, _ = approved_member("contractor", next(_phone), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", next(_phone), onboard=_WORKER)
    job_id = client.post("/api/v1/jobs", json=_JOB, headers=ch).json()["id"]
    app_id = client.post(f"/api/v1/jobs/{job_id}/apply", headers=wh).json()["id"]
    mid = client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch).json()["id"]
    return ch, wh, mid


def test_message_with_phone_is_masked(client: TestClient, approved_member: Member) -> None:
    ch, wh, mid = _confirmed_matching(client, approved_member)
    resp = client.post(
        f"/api/v1/matchings/{mid}/messages",
        json={"body": "電話は09012345678まで"},
        headers=wh,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["was_filtered"] is True
    assert "09012345678" not in body["body"]


def test_clean_message_not_filtered_and_listed(
    client: TestClient, approved_member: Member
) -> None:
    ch, wh, mid = _confirmed_matching(client, approved_member)
    client.post(
        f"/api/v1/matchings/{mid}/messages",
        json={"body": "明日8時に現場でお願いします"},
        headers=wh,
    )
    # The contractor can read the thread too.
    msgs = client.get(f"/api/v1/matchings/{mid}/messages", headers=ch).json()
    assert len(msgs) == 1
    assert msgs[0]["was_filtered"] is False


def test_non_participant_cannot_read_or_send(
    client: TestClient, approved_member: Member
) -> None:
    ch, wh, mid = _confirmed_matching(client, approved_member)
    outsider, _ = approved_member("worker", next(_phone), onboard=_WORKER)
    assert client.get(f"/api/v1/matchings/{mid}/messages", headers=outsider).status_code == 403
    send = client.post(
        f"/api/v1/matchings/{mid}/messages", json={"body": "hi"}, headers=outsider
    )
    assert send.status_code == 403


def test_masking_can_be_disabled_by_config(
    client: TestClient, approved_member: Member, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CRAFTON_CFG__CONTACT_MASK_ENABLED", "false")
    ch, wh, mid = _confirmed_matching(client, approved_member)
    resp = client.post(
        f"/api/v1/matchings/{mid}/messages",
        json={"body": "09012345678"},
        headers=wh,
    )
    body = resp.json()
    assert body["was_filtered"] is False
    assert body["body"] == "09012345678"


def test_empty_body_rejected(client: TestClient, approved_member: Member) -> None:
    ch, wh, mid = _confirmed_matching(client, approved_member)
    resp = client.post(f"/api/v1/matchings/{mid}/messages", json={"body": ""}, headers=wh)
    assert resp.status_code == 422
