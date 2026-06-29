"""Admin can create new admin accounts."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

Member = Callable[..., tuple[dict[str, str], str]]
SeedAdmin = Callable[..., dict[str, str]]
_CONTRACTOR = {"company_name": "ABC", "contact_person": "S", "prefecture": "Tokyo"}


def test_admin_creates_admin_who_can_authenticate(
    client: TestClient, seed_admin: SeedAdmin
) -> None:
    ah = seed_admin("+818000009001")
    resp = client.post(
        "/api/v1/admin/admins",
        json={
            "phone_number": "+819088880001",
            "username": "new_admin",
            "email": "new_admin@crafton.local",
            "password": "admin-password-1",
            "display_name": "New Admin",
        },
        headers=ah,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user_type"] == "admin" and body["status"] == "approved"

    # Appears in the admin list.
    admins = client.get("/api/v1/admin/admins", headers=ah).json()
    assert any(a["phone_number"] == "+819088880001" for a in admins)

    # The new admin can log in with their credentials (username + password).
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "new_admin", "password": "admin-password-1"},
    )
    assert login.status_code == 200, login.text
    new_headers = {"Authorization": f"Bearer {login.json()['token']}"}
    me = client.get("/api/v1/me", headers=new_headers).json()
    assert me["user"]["user_type"] == "admin"
    # And can use an admin-only endpoint.
    assert client.get("/api/v1/admin/admins", headers=new_headers).status_code == 200


def test_create_admin_duplicate_phone_conflicts(
    client: TestClient, seed_admin: SeedAdmin
) -> None:
    ah = seed_admin("+818000009002")
    body = {
        "phone_number": "+819088880002",
        "username": "dup_admin",
        "email": "dup_admin@crafton.local",
        "password": "admin-password-2",
        "display_name": "A",
    }
    assert client.post("/api/v1/admin/admins", json=body, headers=ah).status_code == 201
    dup = client.post("/api/v1/admin/admins", json=body, headers=ah)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "user_exists"


def test_non_admin_cannot_create_admin(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", "+819088880003", onboard=_CONTRACTOR)
    resp = client.post(
        "/api/v1/admin/admins",
        json={
            "phone_number": "+819088880004",
            "username": "x_admin",
            "email": "x_admin@crafton.local",
            "password": "admin-password-3",
            "display_name": "X",
        },
        headers=ch,
    )
    assert resp.status_code == 403
    assert client.get("/api/v1/admin/admins").status_code == 401
