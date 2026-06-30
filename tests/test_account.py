"""Forgot-password reset (via SMS OTP) + account identifier updates.

Registration captures username/email/password and returns a session token; these
exercise the recovery + account-settings paths added on top of that."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.factories import signup_payload

Headers = Callable[..., dict[str, str]]


def _register(client: TestClient, headers: dict[str, str], **over: object) -> dict:
    body = signup_payload(user_type="worker", display_name="Acct", **over)
    resp = client.post("/api/v1/auth/session", json=body, headers=headers)
    assert resp.status_code in (200, 201), resp.text
    return {**body, **resp.json()}


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_reset_password_via_otp(client: TestClient, auth_headers: Headers) -> None:
    phone = "+819012350001"
    reg = _register(client, auth_headers(phone))

    # Re-verify the phone by OTP, then set a new password.
    resp = client.post(
        "/api/v1/auth/reset-password",
        json={"password": "newpass12"},
        headers=auth_headers(phone),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["token"]

    # Old password no longer works; the new one does.
    old = client.post(
        "/api/v1/auth/login",
        json={"identifier": reg["username"], "password": reg["password"]},
    )
    assert old.status_code == 401
    new = client.post(
        "/api/v1/auth/login",
        json={"identifier": reg["username"], "password": "newpass12"},
    )
    assert new.status_code == 200


def test_reset_password_no_account(client: TestClient, auth_headers: Headers) -> None:
    resp = client.post(
        "/api/v1/auth/reset-password",
        json={"password": "newpass12"},
        headers=auth_headers("+819099999999"),
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "reset_no_account"


def test_update_account_changes_identifiers(
    client: TestClient, auth_headers: Headers
) -> None:
    reg = _register(client, auth_headers("+819012350002"))
    resp = client.patch(
        "/api/v1/me/account",
        json={"username": "newhandle", "email": "new@example.com"},
        headers=_bearer(reg["token"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["username"] == "newhandle"
    assert resp.json()["email"] == "new@example.com"

    # The new username logs in with the unchanged password.
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "newhandle", "password": reg["password"]},
    )
    assert login.status_code == 200


def test_update_account_duplicate_rejected(
    client: TestClient, auth_headers: Headers
) -> None:
    a = _register(client, auth_headers("+819012350003"))
    b = _register(client, auth_headers("+819012350004"))
    resp = client.patch(
        "/api/v1/me/account",
        json={"username": a["username"]},
        headers=_bearer(b["token"]),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "username_taken"


def test_update_account_requires_auth(client: TestClient) -> None:
    resp = client.patch("/api/v1/me/account", json={"username": "x"})
    assert resp.status_code == 401
