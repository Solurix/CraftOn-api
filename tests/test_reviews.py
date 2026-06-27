"""Two-way reviews after completion + derived trust/rating (step 7)."""

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

_phone = iter(f"+8190590{i:05d}" for i in range(1, 99999))


def _confirm(client: TestClient, ch: dict[str, str], wh: dict[str, str]) -> str:
    job_id = client.post("/api/v1/jobs", json=_JOB, headers=ch).json()["id"]
    app_id = client.post(f"/api/v1/jobs/{job_id}/apply", headers=wh).json()["id"]
    return client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch).json()["id"]


def _complete(client: TestClient, ch: dict[str, str], wh: dict[str, str]) -> str:
    mid = _confirm(client, ch, wh)
    client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh)
    client.post(f"/api/v1/matchings/{mid}/complete-request", headers=wh)
    client.post(f"/api/v1/matchings/{mid}/approve-completion", headers=ch)
    return mid


def test_review_blocked_before_completion(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", next(_phone), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", next(_phone), onboard=_WORKER)
    mid = _confirm(client, ch, wh)  # confirmed, not completed
    resp = client.post(f"/api/v1/matchings/{mid}/reviews", json={"rating": 5}, headers=ch)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "review_not_allowed"


def test_two_way_reviews_and_duplicate_blocked(
    client: TestClient, approved_member: Member
) -> None:
    ch, cid = approved_member("contractor", next(_phone), onboard=_CONTRACTOR)
    wh, wid = approved_member("worker", next(_phone), onboard=_WORKER)
    mid = _complete(client, ch, wh)

    c2w = client.post(
        f"/api/v1/matchings/{mid}/reviews",
        json={"rating": 5, "comment": "丁寧", "tags": ["punctual"]},
        headers=ch,
    )
    assert c2w.status_code == 201
    assert c2w.json()["direction"] == "contractor_to_worker"
    assert c2w.json()["reviewee_id"] == wid

    w2c = client.post(
        f"/api/v1/matchings/{mid}/reviews", json={"rating": 4}, headers=wh
    )
    assert w2c.status_code == 201
    assert w2c.json()["direction"] == "worker_to_contractor"

    # Duplicate in the same direction is blocked.
    dup = client.post(f"/api/v1/matchings/{mid}/reviews", json={"rating": 1}, headers=ch)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "already_reviewed"

    # Derived display values updated.
    worker = client.get(f"/api/v1/workers/{wid}", headers=ch).json()
    assert float(worker["trust_score"]) == 5.0
    contractor = client.get(f"/api/v1/contractors/{cid}", headers=wh).json()
    assert float(contractor["rating"]) == 4.0


def test_trust_score_is_average_of_ratings(
    client: TestClient, approved_member: Member
) -> None:
    wh, wid = approved_member("worker", next(_phone), onboard=_WORKER)
    ch1, _ = approved_member("contractor", next(_phone), onboard=_CONTRACTOR)
    ch2, _ = approved_member("contractor", next(_phone), onboard=_CONTRACTOR)
    m1 = _complete(client, ch1, wh)
    m2 = _complete(client, ch2, wh)
    client.post(f"/api/v1/matchings/{m1}/reviews", json={"rating": 5}, headers=ch1)
    client.post(f"/api/v1/matchings/{m2}/reviews", json={"rating": 3}, headers=ch2)

    worker = client.get(f"/api/v1/workers/{wid}", headers=ch1).json()
    assert float(worker["trust_score"]) == 4.0  # (5 + 3) / 2

    reviews_list = client.get(f"/api/v1/workers/{wid}/reviews", headers=ch1).json()
    assert len(reviews_list) == 2


def test_non_participant_cannot_review(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", next(_phone), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", next(_phone), onboard=_WORKER)
    outsider, _ = approved_member("contractor", next(_phone), onboard=_CONTRACTOR)
    mid = _complete(client, ch, wh)
    resp = client.post(f"/api/v1/matchings/{mid}/reviews", json={"rating": 5}, headers=outsider)
    assert resp.status_code == 403


def test_rating_out_of_range_rejected(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", next(_phone), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", next(_phone), onboard=_WORKER)
    mid = _complete(client, ch, wh)
    assert client.post(
        f"/api/v1/matchings/{mid}/reviews", json={"rating": 6}, headers=ch
    ).status_code == 422
