"""Admin debug seeder (dev-only random data)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

Member = Callable[..., tuple[dict[str, str], str]]
SeedAdmin = Callable[..., dict[str, str]]
_CONTRACTOR = {"company_name": "ABC", "contact_person": "S", "prefecture": "Tokyo"}


def test_admin_seeds_random_data(client: TestClient, seed_admin: SeedAdmin) -> None:
    ah = seed_admin("+818000007001")
    resp = client.post(
        "/api/v1/admin/debug/seed",
        json={"workers": 4, "contractors": 2, "jobs": 6},
        headers=ah,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"workers": 4, "contractors": 2, "jobs": 6}

    # The seeded users show up in the admin user list.
    users = client.get(
        "/api/v1/admin/users", params={"user_type": "worker"}, headers=ah
    ).json()["items"]
    assert len(users) >= 4
    jobs = client.get("/api/v1/admin/jobs", headers=ah).json()
    assert len(jobs) >= 6


def test_debug_seed_requires_admin(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", "+819099990001", onboard=_CONTRACTOR)
    assert (
        client.post("/api/v1/admin/debug/seed", json={}, headers=ch).status_code == 403
    )
    assert client.post("/api/v1/admin/debug/seed", json={}).status_code == 401
