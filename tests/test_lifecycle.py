"""Day-of lifecycle, fee recording, fee reconciliation, and authZ (step 6)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.factories import Member, confirmed_matching


def test_full_happy_cycle(client: TestClient, approved_member: Member) -> None:
    ch, wh, mid = confirmed_matching(client, approved_member)

    ci = client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh)
    assert ci.status_code == 200 and ci.json()["status"] == "checked_in"
    assert ci.json()["checked_in_at"] is not None

    cr = client.post(f"/api/v1/matchings/{mid}/complete-request", headers=wh)
    assert cr.status_code == 200 and cr.json()["completion_requested_at"] is not None
    assert cr.json()["status"] == "checked_in"  # not completed until approval

    ap = client.post(f"/api/v1/matchings/{mid}/approve-completion", headers=ch)
    assert ap.status_code == 200
    m = ap.json()
    assert m["status"] == "completed"
    assert m["completed_at"] is not None
    # Fee recorded as owed (must-test).
    assert m["platform_fee"] == 3000
    assert m["fee_status"] == "unpaid"


def test_checkin_is_worker_only(client: TestClient, approved_member: Member) -> None:
    ch, wh, mid = confirmed_matching(client, approved_member)
    assert client.post(f"/api/v1/matchings/{mid}/check-in", headers=ch).status_code == 403


def test_approve_requires_completion_request(
    client: TestClient, approved_member: Member
) -> None:
    ch, wh, mid = confirmed_matching(client, approved_member)
    client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh)
    early = client.post(f"/api/v1/matchings/{mid}/approve-completion", headers=ch)
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "completion_not_requested"


def test_complete_request_requires_checkin(
    client: TestClient, approved_member: Member
) -> None:
    ch, wh, mid = confirmed_matching(client, approved_member)
    resp = client.post(f"/api/v1/matchings/{mid}/complete-request", headers=wh)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "not_checked_in"


def test_double_checkin_is_illegal_transition(
    client: TestClient, approved_member: Member
) -> None:
    ch, wh, mid = confirmed_matching(client, approved_member)
    client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh)
    again = client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "illegal_matching_transition"


def test_cancel_then_checkin_illegal(client: TestClient, approved_member: Member) -> None:
    ch, wh, mid = confirmed_matching(client, approved_member)
    canceled = client.post(f"/api/v1/matchings/{mid}/cancel", headers=wh)
    assert canceled.json()["status"] == "canceled"
    assert client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh).status_code == 409


def test_admin_marks_fee_paid(
    client: TestClient, approved_member: Member, seed_admin: Callable[..., dict[str, str]]
) -> None:
    admin = seed_admin()
    ch, wh, mid = confirmed_matching(client, approved_member)
    client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh)
    client.post(f"/api/v1/matchings/{mid}/complete-request", headers=wh)
    client.post(f"/api/v1/matchings/{mid}/approve-completion", headers=ch)

    # Non-admin cannot mark fee paid.
    assert client.post(f"/api/v1/admin/matchings/{mid}/mark-fee-paid", headers=ch).status_code == 403

    paid = client.post(f"/api/v1/admin/matchings/{mid}/mark-fee-paid", headers=admin)
    assert paid.status_code == 200 and paid.json()["fee_status"] == "paid"

    listing = client.get("/api/v1/admin/matchings", params={"fee_status": "paid"}, headers=admin)
    assert any(m["id"] == mid for m in listing.json())
