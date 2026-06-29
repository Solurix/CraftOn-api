"""Returning login (username / email / phone + password) → app session token,
plus the set/replace-password endpoint.

Registration (POST /auth/session) already sets a password and returns a session
token; this exercises the OTP-free returning-login path."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import signup_payload

Headers = Callable[..., dict[str, str]]


def _register(client: TestClient, headers: dict[str, str], **over: object) -> dict:
    """Register a worker and return the request body merged with the response."""
    body = signup_payload(user_type="worker", display_name="PW", **over)
    resp = client.post("/api/v1/auth/session", json=body, headers=headers)
    assert resp.status_code in (200, 201), resp.text
    return {**body, **resp.json()}


def test_login_by_username_email_and_phone(
    client: TestClient, auth_headers: Headers
) -> None:
    phone = "+819012340001"
    reg = _register(client, auth_headers(phone))
    pw = reg["password"]

    # Each identifier — and a case-shifted username/email — logs in.
    for identifier in (reg["username"], reg["email"], phone, reg["username"].upper(), reg["email"].upper()):
        resp = client.post(
            "/api/v1/auth/login", json={"identifier": identifier, "password": pw}
        )
        assert resp.status_code == 200, (identifier, resp.text)
        token = resp.json()["token"]
        me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200 and me.json()["user"]["phone_number"] == phone


def test_login_wrong_password_rejected(
    client: TestClient, auth_headers: Headers
) -> None:
    reg = _register(client, auth_headers("+819012340002"))
    resp = client.post(
        "/api/v1/auth/login", json={"identifier": reg["username"], "password": "wrong"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_login_unknown_identifier_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/login", json={"identifier": "ghost", "password": "whatever"}
    )
    assert resp.status_code == 401


def test_login_without_password_set_rejected(client: TestClient, db: Session) -> None:
    # A user with no password (e.g. legacy/seeded) cannot password-login.
    from app.models.enums import UserType
    from app.models.user import User

    db.add(
        User(
            phone_number="+819012340003",
            username="nopass",
            email="nopass@test.local",
            user_type=UserType.WORKER,
            display_name="NP",
        )
    )
    db.commit()
    resp = client.post(
        "/api/v1/auth/login", json={"identifier": "nopass", "password": "anything"}
    )
    assert resp.status_code == 401


def test_set_password_then_login(client: TestClient, auth_headers: Headers) -> None:
    h = auth_headers("+819012340004")
    reg = _register(client, h)
    assert client.get("/api/v1/me", headers=h).json()["has_password"] is True

    # Rotate the password, then log in with the new one.
    assert (
        client.post(
            "/api/v1/auth/password", json={"password": "rotated-pass"}, headers=h
        ).status_code
        == 204
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"identifier": reg["username"], "password": "rotated-pass"},
    )
    assert resp.status_code == 200, resp.text


def test_set_password_requires_auth(client: TestClient) -> None:
    assert (
        client.post("/api/v1/auth/password", json={"password": "longenough"}).status_code
        == 401
    )


def test_set_password_min_length_enforced(
    client: TestClient, auth_headers: Headers
) -> None:
    h = auth_headers("+819012340005")
    _register(client, h)
    assert (
        client.post(
            "/api/v1/auth/password", json={"password": "short"}, headers=h
        ).status_code
        == 422
    )


def test_suspended_account_cannot_set_password(
    client: TestClient,
    auth_headers: Headers,
    seed_admin: Callable[..., dict[str, str]],
) -> None:
    h = auth_headers("+819012340006")
    reg = _register(client, h)
    admin = seed_admin()
    client.post(
        f"/api/v1/admin/users/{reg['user']['id']}/suspend",
        json={"suspend": True},
        headers=admin,
    )
    # A suspended account may not establish/rotate credentials.
    assert (
        client.post(
            "/api/v1/auth/password", json={"password": "longenough"}, headers=h
        ).status_code
        == 403
    )
