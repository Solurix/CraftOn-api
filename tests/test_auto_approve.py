"""Auto-approve flag: skip manual vetting when ``auto_approve_users`` is on.

Default is OFF (manual vetting). When an admin turns it on, finishing onboarding
approves the account automatically, the existing pending backlog is cleared, and
the visa/insurance gate is still honored (it can't be bypassed by the flag).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from tests.factories import signup_payload

Headers = Callable[..., dict[str, str]]
Admin = Callable[..., dict[str, str]]


def _signup(client: TestClient, headers: dict[str, str], role: str) -> None:
    resp = client.post(
        "/api/v1/auth/session",
        json=signup_payload(user_type=role, display_name=role.title()),
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text


def _set_auto_approve(client: TestClient, admin: dict[str, str], on: bool) -> None:
    resp = client.patch(
        "/api/v1/admin/config",
        json={"updates": {"auto_approve_users": on}},
        headers=admin,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["config"]["auto_approve_users"] is on


def _status(client: TestClient, headers: dict[str, str]) -> str:
    return client.get("/api/v1/me", headers=headers).json()["user"]["status"]


def test_off_by_default_leaves_worker_pending(
    client: TestClient, auth_headers: Headers
) -> None:
    h = auth_headers("+819014440001")
    _signup(client, h, "worker")
    resp = client.post(
        "/api/v1/onboarding/worker",
        json={"nationality": "JP", "worker_class": "employee", "trades": ["大工"]},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending"
    assert _status(client, h) == "pending"


def test_on_approves_worker_on_onboard(
    client: TestClient, auth_headers: Headers, seed_admin: Admin
) -> None:
    _set_auto_approve(client, seed_admin(), True)

    h = auth_headers("+819014440002")
    _signup(client, h, "worker")
    resp = client.post(
        "/api/v1/onboarding/worker",
        json={"nationality": "JP", "worker_class": "employee", "trades": ["大工"]},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"
    assert _status(client, h) == "approved"


def test_on_approves_contractor_on_onboard(
    client: TestClient, auth_headers: Headers, seed_admin: Admin
) -> None:
    _set_auto_approve(client, seed_admin(), True)

    h = auth_headers("+819014440003")
    _signup(client, h, "contractor")
    resp = client.post(
        "/api/v1/onboarding/contractor",
        json={"company_name": "ABC建設", "contact_person": "Suzuki", "prefecture": "Tokyo"},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"


def test_on_still_blocks_worker_failing_visa_gate(
    client: TestClient, auth_headers: Headers, seed_admin: Admin
) -> None:
    """A non-JP worker without a valid visa cannot be auto-approved (compliance)."""
    _set_auto_approve(client, seed_admin(), True)

    h = auth_headers("+819014440004")
    _signup(client, h, "worker")
    resp = client.post(
        "/api/v1/onboarding/worker",
        json={"nationality": "VN", "worker_class": "employee", "trades": ["大工"]},
        headers=h,
    )
    # Onboarding succeeds (profile saved); auto-approval is skipped by the gate.
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending"
    assert _status(client, h) == "pending"


def test_toggle_on_clears_existing_pending_backlog(
    client: TestClient, auth_headers: Headers, seed_admin: Admin
) -> None:
    # A contractor finishes onboarding while the flag is still off → pending.
    h = auth_headers("+819014440005")
    _signup(client, h, "contractor")
    client.post(
        "/api/v1/onboarding/contractor",
        json={"company_name": "Backlog建設", "contact_person": "Tanaka", "prefecture": "Tokyo"},
        headers=h,
    )
    assert _status(client, h) == "pending"

    # Flipping the flag on retroactively approves the waiting account.
    _set_auto_approve(client, seed_admin(), True)
    assert _status(client, h) == "approved"


def test_toggle_on_skips_profileless_pending_user(
    client: TestClient, auth_headers: Headers, seed_admin: Admin
) -> None:
    """A user who signed up but never onboarded has no profile → stays pending."""
    h = auth_headers("+819014440006")
    _signup(client, h, "contractor")  # no onboarding call

    _set_auto_approve(client, seed_admin(), True)
    assert _status(client, h) == "pending"


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


def test_worker_profile_patch_retries_auto_approval(
    client: TestClient, auth_headers: Headers, seed_admin: Admin
) -> None:
    """A worker who first failed the visa gate is auto-approved once they fix
    their visa data via PATCH /workers/me (the flag is on)."""
    _set_auto_approve(client, seed_admin(), True)

    h = auth_headers("+819014440007")
    _signup(client, h, "worker")
    resp = client.post(
        "/api/v1/onboarding/worker",
        json={"nationality": "VN", "worker_class": "employee", "trades": ["大工"]},
        headers=h,
    )
    assert resp.status_code == 200 and resp.json()["status"] == "pending"

    front = _register_doc(client, h, "residence_card_front")
    back = _register_doc(client, h, "residence_card_back")
    patched = client.patch(
        "/api/v1/workers/me",
        json={
            "residence_card_front_doc_id": front,
            "residence_card_back_doc_id": back,
            "visa_expiry_date": "2999-12-31",
        },
        headers=h,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["status"] == "approved"
    assert _status(client, h) == "approved"


def test_worker_profile_patch_leaves_ineligible_worker_pending(
    client: TestClient, auth_headers: Headers, seed_admin: Admin
) -> None:
    _set_auto_approve(client, seed_admin(), True)

    h = auth_headers("+819014440008")
    _signup(client, h, "worker")
    client.post(
        "/api/v1/onboarding/worker",
        json={"nationality": "VN", "worker_class": "employee"},
        headers=h,
    )
    # A profile edit that still fails the gate does not approve.
    patched = client.patch("/api/v1/workers/me", json={"bio": "hi"}, headers=h)
    assert patched.status_code == 200
    assert patched.json()["status"] == "pending"


def test_contractor_profile_patch_retries_auto_approval(
    client: TestClient, auth_headers: Headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flag turned on via the env layer (no admin PATCH → no backlog sweep), so
    the PATCH /contractors/me path itself performs the approval."""
    h = auth_headers("+819014440009")
    _signup(client, h, "contractor")
    client.post(
        "/api/v1/onboarding/contractor",
        json={"company_name": "Late建設", "contact_person": "Mori", "prefecture": "Tokyo"},
        headers=h,
    )
    assert _status(client, h) == "pending"  # flag was off at onboarding time

    monkeypatch.setenv("CRAFTON_CFG__AUTO_APPROVE_USERS", "true")
    patched = client.patch("/api/v1/contractors/me", json={"bio": "hello"}, headers=h)
    assert patched.status_code == 200, patched.text
    assert patched.json()["status"] == "approved"
