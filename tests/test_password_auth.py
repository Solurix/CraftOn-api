"""Password set + OTP-free password login (fake-mode token issuance)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

Headers = Callable[..., dict[str, str]]


def _signup(client: TestClient, headers: dict[str, str], phone: str) -> None:
    resp = client.post(
        "/api/v1/auth/session",
        json={"user_type": "worker", "display_name": "PW"},
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text


def test_set_password_then_login_and_use_token(
    client: TestClient, auth_headers: Headers
) -> None:
    phone = "+819012340001"
    h = auth_headers(phone)
    _signup(client, h, phone)

    # /me reflects no password yet.
    assert client.get("/api/v1/me", headers=h).json()["has_password"] is False

    # Set a password (authenticated).
    assert client.post("/api/v1/auth/password", json={"password": "s3cret-pass"}, headers=h).status_code == 204
    assert client.get("/api/v1/me", headers=h).json()["has_password"] is True

    # Password login (no OTP) returns a usable bearer token.
    resp = client.post(
        "/api/v1/auth/password-login",
        json={"phone_number": phone, "password": "s3cret-pass"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    assert resp.json()["user"]["phone_number"] == phone

    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["user"]["phone_number"] == phone


def test_password_login_wrong_password_rejected(
    client: TestClient, auth_headers: Headers
) -> None:
    phone = "+819012340002"
    h = auth_headers(phone)
    _signup(client, h, phone)
    client.post("/api/v1/auth/password", json={"password": "correct-horse"}, headers=h)

    resp = client.post(
        "/api/v1/auth/password-login",
        json={"phone_number": phone, "password": "wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_password_login_without_set_password_rejected(
    client: TestClient, auth_headers: Headers
) -> None:
    phone = "+819012340003"
    h = auth_headers(phone)
    _signup(client, h, phone)
    # No password set → cannot password-login.
    resp = client.post(
        "/api/v1/auth/password-login",
        json={"phone_number": phone, "password": "anything"},
    )
    assert resp.status_code == 401


def test_set_password_requires_auth(client: TestClient) -> None:
    assert client.post("/api/v1/auth/password", json={"password": "longenough"}).status_code == 401


def test_set_password_min_length_enforced(
    client: TestClient, auth_headers: Headers
) -> None:
    phone = "+819012340004"
    h = auth_headers(phone)
    _signup(client, h, phone)
    assert client.post("/api/v1/auth/password", json={"password": "short"}, headers=h).status_code == 422
