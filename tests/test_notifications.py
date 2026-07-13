"""In-app notifications: created on events, listing, read, count, authZ."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.factories import (
    CONTRACTOR,
    WORKER,
    Member,
    apply_to_job,
    post_job,
    signup_payload,
    unique_phone,
)

Admin = Callable[..., dict[str, str]]


def _types(client: TestClient, headers: dict[str, str]) -> list[str]:
    return [n["type"] for n in client.get("/api/v1/notifications", headers=headers).json()]


def _unread(client: TestClient, headers: dict[str, str]) -> int:
    return client.get("/api/v1/notifications/unread-count", headers=headers).json()["count"]


def test_apply_notifies_contractor(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    wh, _ = approved_member("worker", unique_phone(), onboard=WORKER)
    job_id = post_job(client, ch)
    client.post(f"/api/v1/jobs/{job_id}/apply", headers=wh)

    notes = client.get("/api/v1/notifications", headers=ch).json()
    assert [n["type"] for n in notes] == ["application_received"]
    assert notes[0]["title"] and notes[0]["body"]  # localized, non-empty
    assert notes[0]["link"] == f"/my-jobs/{job_id}"
    assert _unread(client, ch) == 1
    # The worker (actor) gets nothing from their own apply.
    assert _unread(client, wh) == 0


def test_confirm_notifies_worker(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    wh, _ = approved_member("worker", unique_phone(), onboard=WORKER)
    job_id = post_job(client, ch)
    app_id = apply_to_job(client, wh, job_id)
    mid = client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch).json()["id"]

    notes = client.get("/api/v1/notifications", headers=wh).json()
    assert notes[0]["type"] == "application_confirmed"
    assert notes[0]["link"] == f"/matchings/{mid}"


def test_full_cycle_notifications(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    wh, _ = approved_member("worker", unique_phone(), onboard=WORKER)
    job_id = post_job(client, ch)
    app_id = apply_to_job(client, wh, job_id)
    mid = client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch).json()["id"]
    client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh)
    client.post(f"/api/v1/matchings/{mid}/complete-request", headers=wh)
    client.post(f"/api/v1/matchings/{mid}/approve-completion", headers=ch)
    client.post(f"/api/v1/matchings/{mid}/reviews", json={"rating": 5}, headers=ch)

    # Contractor received: application_received, worker_checked_in, completion_requested.
    assert set(_types(client, ch)) == {
        "application_received", "worker_checked_in", "completion_requested",
    }
    # Worker received: application_confirmed, completion_approved, review_received.
    assert set(_types(client, wh)) == {
        "application_confirmed", "completion_approved", "review_received",
    }


def test_mark_read_and_read_all(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    wh, _ = approved_member("worker", unique_phone(), onboard=WORKER)
    job_id = post_job(client, ch)
    app_id = apply_to_job(client, wh, job_id)
    client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch)  # worker: 1
    client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch)  # 409, no extra note

    notes = client.get("/api/v1/notifications", headers=wh).json()
    assert _unread(client, wh) == 1
    read = client.post(f"/api/v1/notifications/{notes[0]['id']}/read", headers=wh)
    assert read.status_code == 200 and read.json()["is_read"] is True
    assert _unread(client, wh) == 0

    # read-all is idempotent and returns how many it flipped.
    assert client.post("/api/v1/notifications/read-all", headers=wh).json()["updated"] == 0


def test_notifications_are_per_user(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    wh, _ = approved_member("worker", unique_phone(), onboard=WORKER)
    outsider, _ = approved_member("worker", unique_phone(), onboard=WORKER)
    job_id = post_job(client, ch)
    client.post(f"/api/v1/jobs/{job_id}/apply", headers=wh)
    assert _unread(client, outsider) == 0

    # Can't mark someone else's notification read.
    nid = client.get("/api/v1/notifications", headers=ch).json()[0]["id"]
    assert client.post(f"/api/v1/notifications/{nid}/read", headers=outsider).status_code == 403


def test_account_approved_notification(
    client: TestClient, auth_headers: Callable[..., dict[str, str]], seed_admin: Admin
) -> None:
    admin = seed_admin()
    wh = auth_headers(unique_phone())
    uid = client.post(
        "/api/v1/auth/session",
        json=signup_payload(user_type="worker", display_name="Taro"),
        headers=wh,
    ).json()["user"]["id"]
    client.post("/api/v1/onboarding/worker", json=WORKER, headers=wh)
    client.post(f"/api/v1/admin/users/{uid}/approve", headers=admin)

    notes = client.get("/api/v1/notifications", headers=wh).json()
    assert notes[0]["type"] == "account_approved"


def test_unauthenticated_cannot_list(client: TestClient) -> None:
    assert client.get("/api/v1/notifications").status_code == 401
