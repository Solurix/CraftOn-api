"""Auth/session wiring: token → user mapping, first-login creation, /me, authZ."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

Headers = Callable[..., dict[str, str]]

PHONE = "+819011112222"


def test_me_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_first_login_requires_role(client: TestClient, auth_headers: Headers) -> None:
    resp = client.post("/api/v1/auth/session", json={}, headers=auth_headers(PHONE))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "role_required"


def test_admin_role_not_self_assignable(client: TestClient, auth_headers: Headers) -> None:
    resp = client.post(
        "/api/v1/auth/session",
        json={"user_type": "admin"},
        headers=auth_headers(PHONE),
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_role"


def test_first_login_creates_worker_then_me_returns_it(
    client: TestClient, auth_headers: Headers
) -> None:
    headers = auth_headers(PHONE)
    created = client.post(
        "/api/v1/auth/session",
        json={"user_type": "worker", "display_name": "Taro"},
        headers=headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["created"] is True
    assert body["user"]["user_type"] == "worker"
    assert body["user"]["status"] == "pending"
    assert body["user"]["display_name"] == "Taro"

    # Second call is idempotent: returns the existing user, created=False.
    again = client.post(
        "/api/v1/auth/session", json={"user_type": "worker"}, headers=headers
    )
    assert again.status_code == 200
    assert again.json()["created"] is False

    me = client.get("/api/v1/me", headers=headers)
    assert me.status_code == 200
    me_body = me.json()
    assert me_body["user"]["phone_number"] == PHONE
    assert me_body["has_worker_profile"] is False


def test_invalid_token_is_unauthorized(client: TestClient) -> None:
    resp = client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-valid-token"})
    assert resp.status_code == 401


def test_error_envelope_localizes_to_accept_language(client: TestClient) -> None:
    resp = client.get("/api/v1/me", headers={"Accept-Language": "en"})
    assert resp.status_code == 401
    assert resp.json()["error"]["message"] == "Authentication required."
