"""Device tracking + revocation (X-Device-Id header), and the admin device list."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.factories import signup_payload

Headers = Callable[..., dict[str, str]]
Admin = Callable[..., dict[str, str]]


def _signup(client: TestClient, headers: dict[str, str]) -> None:
    client.post(
        "/api/v1/auth/session",
        json=signup_payload(user_type="worker", display_name="Dev User"),
        headers=headers,
    )


def test_device_tracked_listed_then_revoked(
    client: TestClient, auth_headers: Headers
) -> None:
    h = auth_headers("+819013330001")
    _signup(client, h)
    dev = {**h, "X-Device-Id": "device-abc", "X-Device-Name": "Chrome on Android"}

    # A request carrying the device header registers the device.
    assert client.get("/api/v1/me", headers=dev).status_code == 200
    listed = client.get("/api/v1/me/devices", headers=dev).json()
    assert len(listed) == 1
    assert listed[0]["device_id"] == "device-abc"
    assert listed[0]["label"] == "Chrome on Android"
    pk = listed[0]["id"]

    # Revoke it; the next request from that device is rejected.
    assert client.post(f"/api/v1/me/devices/{pk}/revoke", headers=h).status_code == 200
    blocked = client.get("/api/v1/me", headers=dev)
    assert blocked.status_code == 401
    # The same user from a non-device client (no header) is unaffected.
    assert client.get("/api/v1/me", headers=h).status_code == 200


def test_no_device_header_tracks_nothing(
    client: TestClient, auth_headers: Headers
) -> None:
    h = auth_headers("+819013330002")
    _signup(client, h)
    client.get("/api/v1/me", headers=h)  # no X-Device-Id
    assert client.get("/api/v1/me/devices", headers=h).json() == []


def test_devices_are_per_user(client: TestClient, auth_headers: Headers) -> None:
    h1 = auth_headers("+819013330003")
    h2 = auth_headers("+819013330004")
    _signup(client, h1)
    _signup(client, h2)
    client.get("/api/v1/me", headers={**h1, "X-Device-Id": "d1"})
    assert len(client.get("/api/v1/me/devices", headers=h1).json()) == 1
    assert client.get("/api/v1/me/devices", headers=h2).json() == []


def test_long_device_name_is_truncated_not_500(
    client: TestClient, auth_headers: Headers
) -> None:
    h = auth_headers("+819013330020")
    _signup(client, h)
    dev = {**h, "X-Device-Id": "longname", "X-Device-Name": "X" * 1000}
    assert client.get("/api/v1/me", headers=dev).status_code == 200
    listed = client.get("/api/v1/me/devices", headers=dev).json()
    assert listed[0]["label"] is not None and len(listed[0]["label"]) == 255


def test_cannot_revoke_another_users_device(
    client: TestClient, auth_headers: Headers
) -> None:
    h1 = auth_headers("+819013330005")
    h2 = auth_headers("+819013330006")
    _signup(client, h1)
    _signup(client, h2)
    client.get("/api/v1/me", headers={**h1, "X-Device-Id": "owned"})
    pk = client.get("/api/v1/me/devices", headers=h1).json()[0]["id"]
    assert client.post(f"/api/v1/me/devices/{pk}/revoke", headers=h2).status_code == 403


def test_admin_sees_all_devices(
    client: TestClient, auth_headers: Headers, seed_admin: Admin
) -> None:
    h = auth_headers("+819013330007")
    _signup(client, h)
    client.get("/api/v1/me", headers={**h, "X-Device-Id": "seen-by-admin", "X-Device-Name": "Phone"})

    admin = seed_admin()
    all_devices = client.get("/api/v1/admin/devices", headers=admin).json()
    mine = [d for d in all_devices if d["device_id"] == "seen-by-admin"]
    assert len(mine) == 1
    assert mine[0]["user_display_name"] == "Dev User"

    # Workers cannot reach the admin device list.
    assert client.get("/api/v1/admin/devices", headers=h).status_code == 403
