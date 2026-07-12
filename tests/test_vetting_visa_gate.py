"""Admin vetting + the visa gate (docs/08) — a must-test compliance rule."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from tests.factories import signup_payload

Headers = Callable[..., dict[str, str]]


def _signup_worker(client: TestClient, headers: dict[str, str], name: str = "W") -> str:
    resp = client.post(
        "/api/v1/auth/session",
        json=signup_payload(user_type="worker", display_name=name),
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["user"]["id"]


def _register_doc(client: TestClient, headers: dict[str, str], doc_type: str) -> str:
    url = client.post(
        "/api/v1/documents/upload-url", json={"doc_type": doc_type}, headers=headers
    ).json()
    reg = client.post(
        "/api/v1/documents",
        json={"doc_type": doc_type, "storage_path": url["storage_path"]},
        headers=headers,
    )
    assert reg.status_code == 201
    return reg.json()["id"]


def _onboard(client: TestClient, headers: dict[str, str], **fields: object) -> None:
    payload = {"nationality": "JP", "worker_class": "employee"}
    payload.update(fields)
    resp = client.post("/api/v1/onboarding/worker", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text


def test_japanese_worker_approved_without_card(
    client: TestClient, auth_headers: Headers, seed_admin: Headers
) -> None:
    admin = seed_admin()
    h = auth_headers("+819022220001")
    uid = _signup_worker(client, h)
    _onboard(client, h, nationality="JP")

    resp = client.post(f"/api/v1/admin/users/{uid}/approve", headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"


def test_non_jp_without_card_is_blocked(
    client: TestClient, auth_headers: Headers, seed_admin: Headers
) -> None:
    admin = seed_admin()
    h = auth_headers("+819022220002")
    uid = _signup_worker(client, h)
    _onboard(client, h, nationality="VN")

    resp = client.post(f"/api/v1/admin/users/{uid}/approve", headers=admin)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "visa_card_required"


def test_non_jp_with_card_but_no_expiry_is_blocked(
    client: TestClient, auth_headers: Headers, seed_admin: Headers
) -> None:
    admin = seed_admin()
    h = auth_headers("+819022220003")
    uid = _signup_worker(client, h)
    front = _register_doc(client, h, "residence_card_front")
    back = _register_doc(client, h, "residence_card_back")
    _onboard(
        client, h, nationality="VN",
        residence_card_front_doc_id=front, residence_card_back_doc_id=back,
    )

    resp = client.post(f"/api/v1/admin/users/{uid}/approve", headers=admin)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "visa_expiry_required"


def test_non_jp_with_expired_visa_is_blocked(
    client: TestClient, auth_headers: Headers, seed_admin: Headers
) -> None:
    admin = seed_admin()
    h = auth_headers("+819022220004")
    uid = _signup_worker(client, h)
    front = _register_doc(client, h, "residence_card_front")
    back = _register_doc(client, h, "residence_card_back")
    _onboard(
        client, h, nationality="VN",
        residence_card_front_doc_id=front, residence_card_back_doc_id=back,
        visa_expiry_date="2000-01-01",
    )

    resp = client.post(f"/api/v1/admin/users/{uid}/approve", headers=admin)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "visa_expired"


def test_non_jp_with_valid_visa_is_approved(
    client: TestClient, auth_headers: Headers, seed_admin: Headers
) -> None:
    admin = seed_admin()
    h = auth_headers("+819022220005")
    uid = _signup_worker(client, h)
    front = _register_doc(client, h, "residence_card_front")
    back = _register_doc(client, h, "residence_card_back")
    _onboard(
        client, h, nationality="VN",
        residence_card_front_doc_id=front, residence_card_back_doc_id=back,
        visa_expiry_date="2999-12-31",
    )

    resp = client.post(f"/api/v1/admin/users/{uid}/approve", headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"


def test_visa_gate_disabled_allows_non_jp_without_card(
    client: TestClient, auth_headers: Headers, seed_admin: Headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRAFTON_CFG__VISA_GATE_ENABLED", "false")
    admin = seed_admin()
    h = auth_headers("+819022220006")
    uid = _signup_worker(client, h)
    _onboard(client, h, nationality="VN")

    resp = client.post(f"/api/v1/admin/users/{uid}/approve", headers=admin)
    assert resp.status_code == 200, resp.text


def test_vetting_queue_lists_pending_and_requires_admin(
    client: TestClient, auth_headers: Headers, seed_admin: Headers
) -> None:
    admin = seed_admin()
    h = auth_headers("+819022220007")
    _signup_worker(client, h)
    _onboard(client, h, nationality="JP")

    # Non-admin is forbidden.
    forbidden = client.get("/api/v1/admin/vetting/queue", headers=h)
    assert forbidden.status_code == 403

    queue = client.get("/api/v1/admin/vetting/queue", headers=admin)
    assert queue.status_code == 200
    phones = [item["user"]["phone_number"] for item in queue.json()["items"]]
    assert "+819022220007" in phones


def test_reject_marks_documents_rejected(
    client: TestClient, auth_headers: Headers, seed_admin: Headers
) -> None:
    admin = seed_admin()
    h = auth_headers("+819022220008")
    uid = _signup_worker(client, h)
    _register_doc(client, h, "photo_id")
    _onboard(client, h, nationality="JP")

    resp = client.post(
        f"/api/v1/admin/users/{uid}/reject",
        json={"reason": "blurry"},
        headers=admin,
    )
    assert resp.status_code == 200
    docs = client.get("/api/v1/documents/me", headers=h).json()
    assert docs[0]["review_status"] == "rejected"
    assert docs[0]["review_note"] == "blurry"


def test_suspend_then_reactivate_approved_worker(
    client: TestClient, auth_headers: Headers, seed_admin: Headers
) -> None:
    admin = seed_admin()
    h = auth_headers("+819022220009")
    uid = _signup_worker(client, h)
    _onboard(client, h, nationality="JP")
    approved = client.post(f"/api/v1/admin/users/{uid}/approve", headers=admin)
    assert approved.json()["status"] == "approved"

    suspended = client.post(
        f"/api/v1/admin/users/{uid}/suspend", json={"suspend": True}, headers=admin
    )
    assert suspended.json()["status"] == "suspended"
    # A suspended worker is blocked from acting.
    blocked = client.post(
        "/api/v1/onboarding/worker",
        json={"nationality": "JP", "worker_class": "employee"},
        headers=h,
    )
    assert blocked.status_code == 403

    # Unsuspending a worker who passes the gate restores approved.
    reactivated = client.post(
        f"/api/v1/admin/users/{uid}/suspend", json={"suspend": False}, headers=admin
    )
    assert reactivated.json()["status"] == "approved"


def test_unsuspend_does_not_force_approve_unvetted_worker(
    client: TestClient, auth_headers: Headers, seed_admin: Headers
) -> None:
    """Suspend→unsuspend must not bypass the visa gate: a pending non-JP worker
    without a card lands back on PENDING, not APPROVED (unsuspend still succeeds)."""
    admin = seed_admin()
    h = auth_headers("+819022220010")
    uid = _signup_worker(client, h)
    _onboard(client, h, nationality="VN")  # no residence card → gate fails

    suspended = client.post(
        f"/api/v1/admin/users/{uid}/suspend", json={"suspend": True}, headers=admin
    )
    assert suspended.json()["status"] == "suspended"

    reactivated = client.post(
        f"/api/v1/admin/users/{uid}/suspend", json={"suspend": False}, headers=admin
    )
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["status"] == "pending"

    # And they remain unapprovable until the gate passes.
    resp = client.post(f"/api/v1/admin/users/{uid}/approve", headers=admin)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "visa_card_required"


def test_unsuspend_profileless_user_lands_on_pending(
    client: TestClient, auth_headers: Headers, seed_admin: Headers
) -> None:
    admin = seed_admin()
    h = auth_headers("+819022220011")
    uid = _signup_worker(client, h)  # never onboarded → no profile

    client.post(f"/api/v1/admin/users/{uid}/suspend", json={"suspend": True}, headers=admin)
    reactivated = client.post(
        f"/api/v1/admin/users/{uid}/suspend", json={"suspend": False}, headers=admin
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["status"] == "pending"


def test_rejected_residence_card_does_not_satisfy_visa_gate(
    client: TestClient, auth_headers: Headers, seed_admin: Headers
) -> None:
    """A rejected card = no card: doc ids on the profile are not enough."""
    admin = seed_admin()
    h = auth_headers("+819022220012")
    uid = _signup_worker(client, h)
    front = _register_doc(client, h, "residence_card_front")
    back = _register_doc(client, h, "residence_card_back")
    _onboard(
        client, h, nationality="VN",
        residence_card_front_doc_id=front, residence_card_back_doc_id=back,
        visa_expiry_date="2999-12-31",
    )

    # Admin rejects the submitted documents (user stays pending, ids stay linked).
    rejected = client.post(
        f"/api/v1/admin/users/{uid}/reject", json={"reason": "unreadable"}, headers=admin
    )
    assert rejected.status_code == 200

    resp = client.post(f"/api/v1/admin/users/{uid}/approve", headers=admin)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "visa_card_required"


def test_approve_does_not_blanket_approve_job_photos(
    client: TestClient, auth_headers: Headers, seed_admin: Headers
) -> None:
    """User vetting reviews identity/compliance documents only. Work photos
    are post-moderated: born ``approved`` at registration (the only approval
    in the product is the per-account decision) and untouched by vetting."""
    admin = seed_admin()
    h = auth_headers("+819022220013")
    uid = _signup_worker(client, h)
    _register_doc(client, h, "photo_id")
    _register_doc(client, h, "job_photo")
    _onboard(client, h, nationality="JP")

    docs = client.get("/api/v1/documents/me", headers=h).json()
    by_type = {d["doc_type"]: d["review_status"] for d in docs}
    assert by_type["photo_id"] == "pending"
    assert by_type["job_photo"] == "approved"  # post-moderated, not vetted

    resp = client.post(f"/api/v1/admin/users/{uid}/approve", headers=admin)
    assert resp.status_code == 200, resp.text

    docs = client.get("/api/v1/documents/me", headers=h).json()
    by_type = {d["doc_type"]: d["review_status"] for d in docs}
    assert by_type["photo_id"] == "approved"
    assert by_type["job_photo"] == "approved"
