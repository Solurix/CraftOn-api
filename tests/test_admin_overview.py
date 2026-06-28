"""Admin overview endpoints: see all users, jobs, and matchings."""

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


def test_admin_lists_all_users_with_profiles(
    client: TestClient, approved_member: Member, seed_admin: Admin
) -> None:
    admin = seed_admin()
    ch, _ = approved_member("contractor", "+819088880001", onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", "+819088880002", onboard=_WORKER)

    items = client.get("/api/v1/admin/users", headers=admin).json()["items"]
    phones = {i["user"]["phone_number"] for i in items}
    assert "+819088880001" in phones and "+819088880002" in phones

    # Worker item carries the embedded profile.
    worker_item = next(i for i in items if i["user"]["phone_number"] == "+819088880002")
    assert worker_item["worker_profile"]["worker_class"] == "employee"

    # Filter by role.
    only_workers = client.get(
        "/api/v1/admin/users", params={"user_type": "worker"}, headers=admin
    ).json()["items"]
    assert only_workers and all(i["user"]["user_type"] == "worker" for i in only_workers)

    # Filter by status.
    approved = client.get(
        "/api/v1/admin/users", params={"status": "approved"}, headers=admin
    ).json()["items"]
    assert all(i["user"]["status"] == "approved" for i in approved)


def test_admin_lists_all_jobs(
    client: TestClient, approved_member: Member, seed_admin: Admin
) -> None:
    admin = seed_admin()
    ch, _ = approved_member("contractor", "+819088880003", onboard=_CONTRACTOR)
    client.post("/api/v1/jobs", json=_JOB, headers=ch)

    jobs = client.get("/api/v1/admin/jobs", headers=admin).json()
    assert len(jobs) >= 1
    assert jobs[0]["contractor_company_name"] == "ABC"
    open_jobs = client.get("/api/v1/admin/jobs", params={"status": "open"}, headers=admin).json()
    assert all(j["status"] == "open" for j in open_jobs)


def test_admin_overview_requires_admin(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", "+819088880004", onboard=_CONTRACTOR)
    assert client.get("/api/v1/admin/users", headers=ch).status_code == 403
    assert client.get("/api/v1/admin/jobs", headers=ch).status_code == 403


def test_admin_matchings_enriched_with_names(
    client: TestClient, approved_member: Member, seed_admin: Admin
) -> None:
    admin = seed_admin()
    ch, _ = approved_member("contractor", "+819088880005", onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", "+819088880006", onboard=_WORKER)
    job_id = client.post("/api/v1/jobs", json=_JOB, headers=ch).json()["id"]
    app_id = client.post(f"/api/v1/jobs/{job_id}/apply", headers=wh).json()["id"]
    client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch)

    rows = client.get("/api/v1/admin/matchings", headers=admin).json()
    assert len(rows) == 1
    assert rows[0]["contractor_company_name"] == "ABC"
    assert rows[0]["work_date"] == "2026-07-01"
