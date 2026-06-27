"""Job posting, search, lifecycle, config-driven gates, and authZ (step 3)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

Member = Callable[..., tuple[dict[str, str], str]]

_CONTRACTOR_ONBOARD = {"company_name": "ABC", "contact_person": "S", "prefecture": "Tokyo"}
_WORKER_ONBOARD = {"nationality": "JP", "worker_class": "employee", "trades": ["大工"]}

_JOB = {
    "trades": ["大工"],
    "work_date": "2026-07-01",
    "start_time": "08:00:00",
    "end_time": "17:00:00",
    "prefecture": "Tokyo",
    "daily_wage": 18000,
    "headcount": 2,
    "notes": "安全第一",
}


def test_contractor_posts_and_lists_own_job(
    client: TestClient, approved_member: Member
) -> None:
    h, _ = approved_member("contractor", "+819033330001", onboard=_CONTRACTOR_ONBOARD)
    resp = client.post("/api/v1/jobs", json=_JOB, headers=h)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "open"
    assert body["daily_wage"] == 18000
    assert body["contractor_company_name"] == "ABC"

    mine = client.get("/api/v1/jobs/mine", headers=h).json()
    assert len(mine) == 1


def test_worker_cannot_post_job(client: TestClient, approved_member: Member) -> None:
    h, _ = approved_member("worker", "+819033330002", onboard=_WORKER_ONBOARD)
    resp = client.post("/api/v1/jobs", json=_JOB, headers=h)
    assert resp.status_code == 403


def test_worker_searches_open_jobs_with_filters(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", "+819033330003", onboard=_CONTRACTOR_ONBOARD)
    client.post("/api/v1/jobs", json=_JOB, headers=ch)
    client.post(
        "/api/v1/jobs",
        json={**_JOB, "prefecture": "Osaka", "trades": ["電気"]},
        headers=ch,
    )

    wh, _ = approved_member("worker", "+819033330004", onboard=_WORKER_ONBOARD)
    all_jobs = client.get("/api/v1/jobs", headers=wh).json()
    assert len(all_jobs) == 2
    tokyo = client.get("/api/v1/jobs", params={"prefecture": "Tokyo"}, headers=wh).json()
    assert len(tokyo) == 1
    daiku = client.get("/api/v1/jobs", params={"trade": "大工"}, headers=wh).json()
    assert len(daiku) == 1 and daiku[0]["prefecture"] == "Tokyo"


def test_invalid_times_rejected(client: TestClient, approved_member: Member) -> None:
    h, _ = approved_member("contractor", "+819033330005", onboard=_CONTRACTOR_ONBOARD)
    resp = client.post(
        "/api/v1/jobs",
        json={**_JOB, "start_time": "17:00:00", "end_time": "08:00:00"},
        headers=h,
    )
    assert resp.status_code == 422


def test_service_area_enforced_when_configured(
    client: TestClient, approved_member: Member, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CRAFTON_CFG__SERVICE_AREA_ENFORCE", "true")
    h, _ = approved_member("contractor", "+819033330006", onboard=_CONTRACTOR_ONBOARD)
    # Default service area is Tokyo/Kanagawa/Saitama/Chiba — Osaka is out.
    resp = client.post("/api/v1/jobs", json={**_JOB, "prefecture": "Osaka"}, headers=h)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "out_of_service_area"
    # Tokyo is allowed.
    ok = client.post("/api/v1/jobs", json=_JOB, headers=h)
    assert ok.status_code == 201


def test_allowed_trades_enforced_when_configured(
    client: TestClient, approved_member: Member, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CRAFTON_CFG__ALLOWED_TRADES", '["電気"]')
    h, _ = approved_member("contractor", "+819033330007", onboard=_CONTRACTOR_ONBOARD)
    resp = client.post("/api/v1/jobs", json=_JOB, headers=h)  # 大工 not allowed
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "trade_not_allowed"


def test_only_owner_can_edit_and_cancel(
    client: TestClient, approved_member: Member
) -> None:
    owner, _ = approved_member("contractor", "+819033330008", onboard=_CONTRACTOR_ONBOARD)
    other, _ = approved_member("contractor", "+819033330009", onboard=_CONTRACTOR_ONBOARD)
    job_id = client.post("/api/v1/jobs", json=_JOB, headers=owner).json()["id"]

    forbidden = client.patch(
        f"/api/v1/jobs/{job_id}", json={"daily_wage": 20000}, headers=other
    )
    assert forbidden.status_code == 403

    edited = client.patch(
        f"/api/v1/jobs/{job_id}", json={"daily_wage": 20000}, headers=owner
    )
    assert edited.status_code == 200 and edited.json()["daily_wage"] == 20000

    canceled = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=owner)
    assert canceled.status_code == 200 and canceled.json()["status"] == "canceled"
    # Canceled job no longer appears in worker search.
    wh, _ = approved_member("worker", "+819033330010", onboard=_WORKER_ONBOARD)
    assert client.get("/api/v1/jobs", headers=wh).json() == []
