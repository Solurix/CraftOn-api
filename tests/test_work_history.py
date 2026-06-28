"""Worker work history: completed matchings + earnings totals (worker-only)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

Member = Callable[..., tuple[dict[str, str], str]]

_CONTRACTOR = {"company_name": "ABC", "contact_person": "S", "prefecture": "Tokyo"}
_WORKER = {"nationality": "JP", "worker_class": "employee", "trades": ["大工"]}
_JOB = {
    "trades": ["大工"], "work_date": "2026-07-01",
    "start_time": "08:00:00", "end_time": "17:00:00",
    "prefecture": "Tokyo", "daily_wage": 18000, "headcount": 1,
}

_phone = iter(f"+8190595{i:05d}" for i in range(1, 99999))


def _confirm(client: TestClient, ch: dict[str, str], wh: dict[str, str], **over: object) -> str:
    job_id = client.post("/api/v1/jobs", json={**_JOB, **over}, headers=ch).json()["id"]
    app_id = client.post(f"/api/v1/jobs/{job_id}/apply", headers=wh).json()["id"]
    return client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch).json()["id"]


def _complete(client: TestClient, ch: dict[str, str], wh: dict[str, str], **over: object) -> str:
    mid = _confirm(client, ch, wh, **over)
    client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh)
    client.post(f"/api/v1/matchings/{mid}/complete-request", headers=wh)
    client.post(f"/api/v1/matchings/{mid}/approve-completion", headers=ch)
    return mid


def test_history_lists_only_completed_with_totals(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", next(_phone), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", next(_phone), onboard=_WORKER)

    # Two completed jobs (different wages) + one merely confirmed (not completed).
    _complete(client, ch, wh, daily_wage=18000, work_date="2026-07-01")
    _complete(client, ch, wh, daily_wage=22000, work_date="2026-07-08")
    _confirm(client, ch, wh, work_date="2026-07-15")

    body = client.get("/api/v1/matchings/history", headers=wh).json()
    assert body["completed_count"] == 2
    assert body["total_earned"] == 40000
    assert all(m["status"] == "completed" for m in body["matchings"])
    # Most recent work date first.
    assert [m["work_date"] for m in body["matchings"]] == ["2026-07-08", "2026-07-01"]


def test_history_empty_for_new_worker(
    client: TestClient, approved_member: Member
) -> None:
    wh, _ = approved_member("worker", next(_phone), onboard=_WORKER)
    body = client.get("/api/v1/matchings/history", headers=wh).json()
    assert body == {"completed_count": 0, "total_earned": 0, "matchings": []}


def test_history_is_per_worker(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", next(_phone), onboard=_CONTRACTOR)
    w1, _ = approved_member("worker", next(_phone), onboard=_WORKER)
    w2, _ = approved_member("worker", next(_phone), onboard=_WORKER)
    _complete(client, ch, w1)
    assert client.get("/api/v1/matchings/history", headers=w1).json()["completed_count"] == 1
    assert client.get("/api/v1/matchings/history", headers=w2).json()["completed_count"] == 0


def test_history_is_worker_only(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", next(_phone), onboard=_CONTRACTOR)
    assert client.get("/api/v1/matchings/history", headers=ch).status_code == 403
    assert client.get("/api/v1/matchings/history").status_code == 401
