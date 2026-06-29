"""End-to-end happy path at the API level (docs/04 §1 definition of done).

post job → apply → confirm → check-in → complete → approve → fee → reviews,
with admin vetting and a masked chat message along the way. Deterministic and
fast (no browser); complements the Playwright UI E2E.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.factories import signup_payload

Headers = Callable[..., dict[str, str]]
Admin = Callable[..., dict[str, str]]


def _signup(client: TestClient, headers: dict[str, str], role: str, name: str) -> str:
    resp = client.post(
        "/api/v1/auth/session",
        json=signup_payload(user_type=role, display_name=name),
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["user"]["id"]


def test_full_cycle(
    client: TestClient, auth_headers: Headers, seed_admin: Admin
) -> None:
    admin = seed_admin()

    # 1. Contractor signs up, onboards, gets approved.
    ch = auth_headers("+819000010001")
    cid = _signup(client, ch, "contractor", "ABC建設")
    client.post(
        "/api/v1/onboarding/contractor",
        json={"company_name": "ABC建設", "contact_person": "Suzuki", "prefecture": "Tokyo"},
        headers=ch,
    )
    assert client.post(f"/api/v1/admin/users/{cid}/approve", headers=admin).status_code == 200

    # 2. Worker signs up (JP employee), onboards, gets approved.
    wh = auth_headers("+819000010002")
    wid = _signup(client, wh, "worker", "Taro")
    client.post(
        "/api/v1/onboarding/worker",
        json={"nationality": "JP", "worker_class": "employee", "trades": ["大工"]},
        headers=wh,
    )
    assert client.post(f"/api/v1/admin/users/{wid}/approve", headers=admin).status_code == 200

    # 3. Contractor posts a job; worker finds it and applies.
    job = client.post(
        "/api/v1/jobs",
        json={
            "trades": ["大工"], "work_date": "2026-07-01",
            "start_time": "08:00:00", "end_time": "17:00:00",
            "prefecture": "Tokyo", "daily_wage": 18000, "headcount": 1,
        },
        headers=ch,
    ).json()
    found = client.get("/api/v1/jobs", params={"trade": "大工"}, headers=wh).json()
    assert any(j["id"] == job["id"] for j in found)
    application = client.post(f"/api/v1/jobs/{job['id']}/apply", headers=wh).json()

    # 4. Contractor confirms → matching (employee → day-labor, ¥3,000 fee).
    matching = client.post(
        f"/api/v1/applications/{application['id']}/confirm", headers=ch
    ).json()
    assert matching["status"] == "confirmed"
    assert matching["contract_type"] == "employment_daylabor"
    assert matching["platform_fee"] == 3000 and matching["fee_status"] == "unpaid"
    mid = matching["id"]

    # 5. Chat: a phone number is masked server-side.
    msg = client.post(
        f"/api/v1/matchings/{mid}/messages",
        json={"body": "現場の電話は09012345678です"},
        headers=ch,
    ).json()
    assert msg["was_filtered"] is True and "09012345678" not in msg["body"]

    # 6. Day-of: worker checks in, reports completion, contractor approves.
    assert client.post(f"/api/v1/matchings/{mid}/check-in", headers=wh).json()["status"] == "checked_in"
    client.post(f"/api/v1/matchings/{mid}/complete-request", headers=wh)
    completed = client.post(f"/api/v1/matchings/{mid}/approve-completion", headers=ch).json()
    assert completed["status"] == "completed" and completed["completed_at"] is not None

    # 7. Admin reconciles the fee.
    assert client.post(f"/api/v1/admin/matchings/{mid}/mark-fee-paid", headers=admin).json()["fee_status"] == "paid"

    # 8. Both leave reviews; derived display values update.
    client.post(f"/api/v1/matchings/{mid}/reviews", json={"rating": 5}, headers=ch)
    client.post(f"/api/v1/matchings/{mid}/reviews", json={"rating": 4}, headers=wh)
    assert float(client.get(f"/api/v1/workers/{wid}", headers=ch).json()["trust_score"]) == 5.0
    assert float(client.get(f"/api/v1/contractors/{cid}", headers=wh).json()["rating"]) == 4.0
