"""Worker work history: completed matchings + earnings totals (worker-only)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.factories import (
    CONTRACTOR,
    WORKER,
    Member,
    complete_matching,
    confirm_matching,
    unique_phone,
)


def test_history_lists_only_completed_with_totals(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    wh, _ = approved_member("worker", unique_phone(), onboard=WORKER)

    # Two completed jobs (different wages) + one merely confirmed (not completed).
    complete_matching(client, ch, wh, daily_wage=18000, work_date="2026-07-01")
    complete_matching(client, ch, wh, daily_wage=22000, work_date="2026-07-08")
    confirm_matching(client, ch, wh, work_date="2026-07-15")

    body = client.get("/api/v1/matchings/history", headers=wh).json()
    assert body["completed_count"] == 2
    assert body["total_earned"] == 40000
    assert all(m["status"] == "completed" for m in body["matchings"])
    # Most recent work date first.
    assert [m["work_date"] for m in body["matchings"]] == ["2026-07-08", "2026-07-01"]


def test_history_empty_for_new_worker(
    client: TestClient, approved_member: Member
) -> None:
    wh, _ = approved_member("worker", unique_phone(), onboard=WORKER)
    body = client.get("/api/v1/matchings/history", headers=wh).json()
    assert body == {"completed_count": 0, "total_earned": 0, "matchings": []}


def test_history_is_per_worker(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    w1, _ = approved_member("worker", unique_phone(), onboard=WORKER)
    w2, _ = approved_member("worker", unique_phone(), onboard=WORKER)
    complete_matching(client, ch, w1)
    assert client.get("/api/v1/matchings/history", headers=w1).json()["completed_count"] == 1
    assert client.get("/api/v1/matchings/history", headers=w2).json()["completed_count"] == 0


def test_history_is_worker_only(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    assert client.get("/api/v1/matchings/history", headers=ch).status_code == 403
    assert client.get("/api/v1/matchings/history").status_code == 401
