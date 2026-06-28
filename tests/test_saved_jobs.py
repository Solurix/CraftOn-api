"""Saved jobs: a worker bookmarks jobs to revisit later (worker-only, idempotent)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.services import saved_jobs

Member = Callable[..., tuple[dict[str, str], str]]

_CONTRACTOR = {"company_name": "ABC", "contact_person": "S", "prefecture": "Tokyo"}
_EMPLOYEE = {"nationality": "JP", "worker_class": "employee", "trades": ["大工"]}
_JOB = {
    "trades": ["大工"], "work_date": "2026-07-01",
    "start_time": "08:00:00", "end_time": "17:00:00",
    "prefecture": "Tokyo", "daily_wage": 18000, "headcount": 2,
}

_phone = iter(f"+8190551{i:05d}" for i in range(1, 99999))


def _next_phone() -> str:
    return next(_phone)


def _post_job(client: TestClient, ch: dict[str, str]) -> str:
    return client.post("/api/v1/jobs", json=_JOB, headers=ch).json()["id"]


def test_save_then_appears_in_saved_list_and_ids(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", _next_phone(), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", _next_phone(), onboard=_EMPLOYEE)
    job_id = _post_job(client, ch)

    assert client.put(f"/api/v1/jobs/{job_id}/save", headers=wh).status_code == 204

    saved = client.get("/api/v1/jobs/saved", headers=wh).json()
    assert [j["id"] for j in saved] == [job_id]
    assert client.get("/api/v1/jobs/saved-ids", headers=wh).json() == [job_id]


def test_save_is_idempotent(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", _next_phone(), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", _next_phone(), onboard=_EMPLOYEE)
    job_id = _post_job(client, ch)

    assert client.put(f"/api/v1/jobs/{job_id}/save", headers=wh).status_code == 204
    assert client.put(f"/api/v1/jobs/{job_id}/save", headers=wh).status_code == 204
    assert len(client.get("/api/v1/jobs/saved", headers=wh).json()) == 1


def test_unsave_removes_and_is_idempotent(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", _next_phone(), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", _next_phone(), onboard=_EMPLOYEE)
    job_id = _post_job(client, ch)

    client.put(f"/api/v1/jobs/{job_id}/save", headers=wh)
    assert client.delete(f"/api/v1/jobs/{job_id}/save", headers=wh).status_code == 204
    assert client.get("/api/v1/jobs/saved", headers=wh).json() == []
    # Unsaving again is a no-op, not an error.
    assert client.delete(f"/api/v1/jobs/{job_id}/save", headers=wh).status_code == 204


def test_save_unknown_job_404(client: TestClient, approved_member: Member) -> None:
    wh, _ = approved_member("worker", _next_phone(), onboard=_EMPLOYEE)
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.put(f"/api/v1/jobs/{missing}/save", headers=wh).status_code == 404


def test_contractor_cannot_save(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", _next_phone(), onboard=_CONTRACTOR)
    job_id = _post_job(client, ch)
    assert client.put(f"/api/v1/jobs/{job_id}/save", headers=ch).status_code == 403
    assert client.get("/api/v1/jobs/saved", headers=ch).status_code == 403


def test_saved_jobs_are_per_worker(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", _next_phone(), onboard=_CONTRACTOR)
    w1, _ = approved_member("worker", _next_phone(), onboard=_EMPLOYEE)
    w2, _ = approved_member("worker", _next_phone(), onboard=_EMPLOYEE)
    job_id = _post_job(client, ch)

    client.put(f"/api/v1/jobs/{job_id}/save", headers=w1)
    assert len(client.get("/api/v1/jobs/saved", headers=w1).json()) == 1
    assert client.get("/api/v1/jobs/saved", headers=w2).json() == []


def test_save_requires_auth(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", _next_phone(), onboard=_CONTRACTOR)
    job_id = _post_job(client, ch)
    assert client.put(f"/api/v1/jobs/{job_id}/save").status_code == 401
    assert client.get("/api/v1/jobs/saved").status_code == 401


def test_concurrent_duplicate_save_is_handled(
    client: TestClient, approved_member: Member, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Simulate a save race: force both calls past the "already saved?" pre-check
    # so the second insert hits the unique constraint. It must be swallowed as an
    # idempotent no-op (204), not surface as a 500.
    ch, _ = approved_member("contractor", _next_phone(), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", _next_phone(), onboard=_EMPLOYEE)
    job_id = _post_job(client, ch)
    monkeypatch.setattr(saved_jobs, "_saved_row", lambda *a, **k: None)

    assert client.put(f"/api/v1/jobs/{job_id}/save", headers=wh).status_code == 204
    assert client.put(f"/api/v1/jobs/{job_id}/save", headers=wh).status_code == 204
    monkeypatch.undo()
    assert len(client.get("/api/v1/jobs/saved", headers=wh).json()) == 1
