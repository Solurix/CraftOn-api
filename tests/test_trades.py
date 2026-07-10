"""Trade catalog: list, admin CRUD, custom-value aggregation, and merge."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

Member = Callable[..., tuple[dict[str, str], str]]
AdminSeed = Callable[..., dict[str, str]]

_CONTRACTOR = {"company_name": "ABC", "contact_person": "S", "prefecture": "Tokyo"}
_JOB = {
    "trades": ["大工"], "work_date": "2026-08-01",
    "start_time": "08:00:00", "end_time": "17:00:00",
    "prefecture": "Tokyo", "daily_wage": 18000, "headcount": 1,
}


def _mk_trade(client: TestClient, ah: dict[str, str], ja: str, en: str) -> dict:
    resp = client.post(
        "/api/v1/admin/trades", json={"name_ja": ja, "name_en": en}, headers=ah
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_trades_list_requires_auth_and_returns_catalog(
    client: TestClient, approved_member: Member, seed_admin: AdminSeed
) -> None:
    assert client.get("/api/v1/trades").status_code == 401

    ah = seed_admin("+818000010001")
    _mk_trade(client, ah, "大工", "Carpenter")
    _mk_trade(client, ah, "左官", "Plasterer")

    wh, _ = approved_member(
        "worker", "+819060010001", onboard={"nationality": "JP", "worker_class": "employee"}
    )
    body = client.get("/api/v1/trades", headers=wh).json()
    names = {(t["name_ja"], t["name_en"]) for t in body}
    assert ("大工", "Carpenter") in names and ("左官", "Plasterer") in names


def test_admin_trade_crud_and_dedup(client: TestClient, seed_admin: AdminSeed) -> None:
    ah = seed_admin("+818000010002")
    t = _mk_trade(client, ah, "配管", "Plumber")
    # Duplicate canonical name → 409.
    dup = client.post(
        "/api/v1/admin/trades", json={"name_ja": "配管", "name_en": "x"}, headers=ah
    )
    assert dup.status_code == 409

    upd = client.patch(
        f"/api/v1/admin/trades/{t['id']}",
        json={"name_en": "Plumbing", "active": False},
        headers=ah,
    )
    assert upd.status_code == 200
    assert upd.json()["name_en"] == "Plumbing" and upd.json()["active"] is False


def test_custom_trades_aggregation_and_merge(
    client: TestClient, approved_member: Member, seed_admin: AdminSeed
) -> None:
    ah = seed_admin("+818000010003")
    canonical = _mk_trade(client, ah, "電気工", "Electrician")

    # Two workers + one job using a free-text variant of "electrician".
    w1, _ = approved_member(
        "worker", "+819060010002",
        onboard={"nationality": "JP", "worker_class": "employee", "trades": ["でんき", "大工"]},
    )
    w2, _ = approved_member(
        "worker", "+819060010003",
        onboard={"nationality": "JP", "worker_class": "employee", "trades": ["でんき"]},
    )
    ch, _ = approved_member("contractor", "+819060010004", onboard=_CONTRACTOR)
    job_id = client.post(
        "/api/v1/jobs", json={**_JOB, "trades": ["でんき"]}, headers=ch
    ).json()["id"]

    custom = client.get("/api/v1/admin/trades/custom", headers=ah).json()
    entry = next(c for c in custom if c["name"] == "でんき")
    assert entry["worker_count"] == 2 and entry["job_count"] == 1

    merged = client.post(
        "/api/v1/admin/trades/merge",
        json={"from_name": "でんき", "into_trade_id": canonical["id"]},
        headers=ah,
    )
    assert merged.status_code == 200, merged.text
    assert merged.json() == {
        "workers_updated": 2,
        "jobs_updated": 1,
        "canonical_name": "電気工",
    }

    # Rewritten (deduplicated, order preserved) on profiles and the job.
    me1 = client.get("/api/v1/me", headers=w1).json()["worker_profile"]
    assert me1["trades"] == ["電気工", "大工"]
    job = client.get(f"/api/v1/jobs/{job_id}", headers=w1).json()
    assert job["trades"] == ["電気工"]

    # The value no longer shows up as custom.
    left = client.get("/api/v1/admin/trades/custom", headers=ah).json()
    assert all(c["name"] != "でんき" for c in left)


def test_trades_admin_endpoints_forbidden_for_members(
    client: TestClient, approved_member: Member
) -> None:
    wh, _ = approved_member(
        "worker", "+819060010005", onboard={"nationality": "JP", "worker_class": "employee"}
    )
    assert client.get("/api/v1/admin/trades", headers=wh).status_code == 403
    assert (
        client.post(
            "/api/v1/admin/trades", json={"name_ja": "x", "name_en": "y"}, headers=wh
        ).status_code
        == 403
    )
