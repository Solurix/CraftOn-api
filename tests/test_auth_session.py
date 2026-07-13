"""Auth/session wiring: token → user mapping, first-login creation, /me, authZ."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.factories import signup_payload

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
    reg = signup_payload(user_type="worker", display_name="Taro")
    created = client.post("/api/v1/auth/session", json=reg, headers=headers)
    assert created.status_code == 201
    body = created.json()
    assert body["created"] is True
    assert body["user"]["user_type"] == "worker"
    assert body["user"]["status"] == "pending"
    assert body["user"]["display_name"] == "Taro"
    assert body["user"]["username"] == reg["username"]
    assert body["user"]["email"] == reg["email"]
    # Registration logs the user in: a session token is returned.
    assert body["token"]

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


def test_first_login_requires_credentials(
    client: TestClient, auth_headers: Headers
) -> None:
    # Role present but no username/email/password → registration is rejected.
    resp = client.post(
        "/api/v1/auth/session",
        json={"user_type": "worker", "display_name": "NoCreds"},
        headers=auth_headers(PHONE),
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "credentials_required"


def test_duplicate_username_and_email_conflict(
    client: TestClient, auth_headers: Headers
) -> None:
    first = signup_payload(user_type="worker", display_name="A")
    assert (
        client.post(
            "/api/v1/auth/session", json=first, headers=auth_headers("+819000000001")
        ).status_code
        == 201
    )

    # Same username (different phone/email) → 409 username_taken.
    dup_user = signup_payload(
        user_type="worker", display_name="B", username=first["username"]
    )
    r1 = client.post(
        "/api/v1/auth/session", json=dup_user, headers=auth_headers("+819000000002")
    )
    assert r1.status_code == 409 and r1.json()["error"]["code"] == "username_taken"

    # Same email → 409 email_taken.
    dup_email = signup_payload(
        user_type="worker", display_name="C", email=first["email"]
    )
    r2 = client.post(
        "/api/v1/auth/session", json=dup_email, headers=auth_headers("+819000000003")
    )
    assert r2.status_code == 409 and r2.json()["error"]["code"] == "email_taken"


def test_session_language_switch(client: TestClient, auth_headers: Headers) -> None:
    headers = auth_headers("+819011113333")
    reg = signup_payload(user_type="worker", preferred_language="ja")
    assert client.post("/api/v1/auth/session", json=reg, headers=headers).status_code == 201

    # A returning call may switch the stored language; the response reflects it.
    switched = client.post(
        "/api/v1/auth/session", json={"preferred_language": "en"}, headers=headers
    )
    assert switched.status_code == 200
    assert switched.json()["user"]["preferred_language"] == "en"

    # Subsequent errors render in the newly chosen locale (pending worker → 403).
    err = client.get("/api/v1/matchings/history", headers=headers)
    assert err.status_code == 403
    assert err.json()["error"]["message"] == "Your account must be approved before doing this."

    # An unsupported locale is ignored, not stored.
    ignored = client.post(
        "/api/v1/auth/session", json={"preferred_language": "fr"}, headers=headers
    )
    assert ignored.status_code == 200
    assert ignored.json()["user"]["preferred_language"] == "en"


def test_invalid_token_is_unauthorized(client: TestClient) -> None:
    resp = client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-valid-token"})
    assert resp.status_code == 401


def test_error_envelope_localizes_to_accept_language(client: TestClient) -> None:
    resp = client.get("/api/v1/me", headers={"Accept-Language": "en"})
    assert resp.status_code == 401
    assert resp.json()["error"]["message"] == "Authentication required."
