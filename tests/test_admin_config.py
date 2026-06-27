"""Admin config endpoints: runtime override path + precedence into behavior."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

Member = Callable[..., tuple[dict[str, str], str]]
Admin = Callable[..., dict[str, str]]

_CONTRACTOR = {"company_name": "ABC", "contact_person": "S", "prefecture": "Tokyo"}
_WORKER = {"nationality": "JP", "worker_class": "employee", "trades": ["大工"]}
_JOB = {
    "trades": ["大工"], "work_date": "2026-07-01",
    "start_time": "08:00:00", "end_time": "17:00:00",
    "prefecture": "Tokyo", "daily_wage": 18000, "headcount": 1,
}

_phone = iter(f"+8190580{i:05d}" for i in range(1, 99999))


def test_read_config_snapshot(client: TestClient, seed_admin: Admin) -> None:
    admin = seed_admin()
    resp = client.get("/api/v1/admin/config", headers=admin)
    assert resp.status_code == 200
    cfg = resp.json()["config"]
    assert cfg["platform_fee_per_match"] == 3000
    assert cfg["contact_mask_enabled"] is True


def test_non_admin_cannot_read_or_update_config(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", next(_phone), onboard=_CONTRACTOR)
    assert client.get("/api/v1/admin/config", headers=ch).status_code == 403
    assert client.patch(
        "/api/v1/admin/config", json={"updates": {"platform_fee_per_match": 1}}, headers=ch
    ).status_code == 403


def test_unknown_config_key_rejected(client: TestClient, seed_admin: Admin) -> None:
    admin = seed_admin()
    resp = client.patch(
        "/api/v1/admin/config", json={"updates": {"nope": 1}}, headers=admin
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unknown_config_key"


def test_runtime_override_changes_fee_behavior(
    client: TestClient, approved_member: Member, seed_admin: Admin
) -> None:
    admin = seed_admin()
    # Admin raises the platform fee at runtime (app_config override).
    patched = client.patch(
        "/api/v1/admin/config",
        json={"updates": {"platform_fee_per_match": 5000}},
        headers=admin,
    )
    assert patched.status_code == 200
    assert patched.json()["config"]["platform_fee_per_match"] == 5000

    # A subsequent confirm uses the overridden fee (precedence: app_config > default).
    ch, _ = approved_member("contractor", next(_phone), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", next(_phone), onboard=_WORKER)
    job_id = client.post("/api/v1/jobs", json=_JOB, headers=ch).json()["id"]
    app_id = client.post(f"/api/v1/jobs/{job_id}/apply", headers=wh).json()["id"]
    matching = client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch).json()
    assert matching["platform_fee"] == 5000
