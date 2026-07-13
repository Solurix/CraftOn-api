"""Chat endpoint: server-side masking is authoritative, plus participant authZ."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.factories import WORKER, Member, confirmed_matching, unique_phone


def test_message_with_phone_is_masked(client: TestClient, approved_member: Member) -> None:
    ch, wh, mid = confirmed_matching(client, approved_member)
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
    ch, wh, mid = confirmed_matching(client, approved_member)
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
    ch, wh, mid = confirmed_matching(client, approved_member)
    outsider, _ = approved_member("worker", unique_phone(), onboard=WORKER)
    assert client.get(f"/api/v1/matchings/{mid}/messages", headers=outsider).status_code == 403
    send = client.post(
        f"/api/v1/matchings/{mid}/messages", json={"body": "hi"}, headers=outsider
    )
    assert send.status_code == 403


def test_masking_can_be_disabled_by_config(
    client: TestClient, approved_member: Member, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CRAFTON_CFG__CONTACT_MASK_ENABLED", "false")
    ch, wh, mid = confirmed_matching(client, approved_member)
    resp = client.post(
        f"/api/v1/matchings/{mid}/messages",
        json={"body": "09012345678"},
        headers=wh,
    )
    body = resp.json()
    assert body["was_filtered"] is False
    assert body["body"] == "09012345678"


def test_empty_body_rejected(client: TestClient, approved_member: Member) -> None:
    ch, wh, mid = confirmed_matching(client, approved_member)
    resp = client.post(f"/api/v1/matchings/{mid}/messages", json={"body": ""}, headers=wh)
    assert resp.status_code == 422
