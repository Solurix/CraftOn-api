"""Applications + confirm: routing, gates, fee recording, authZ (step 4)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

Member = Callable[..., tuple[dict[str, str], str]]

_CONTRACTOR = {"company_name": "ABC", "contact_person": "S", "prefecture": "Tokyo"}
_EMPLOYEE = {"nationality": "JP", "worker_class": "employee", "trades": ["大工"]}
_FREELANCE_INSURED = {
    "nationality": "JP", "worker_class": "freelance", "has_insurance": True,
}
_FREELANCE_UNINSURED = {
    "nationality": "JP", "worker_class": "freelance", "has_insurance": False,
}
_JOB = {
    "trades": ["大工"], "work_date": "2026-07-01",
    "start_time": "08:00:00", "end_time": "17:00:00",
    "prefecture": "Tokyo", "daily_wage": 18000, "headcount": 2,
}

_phone = iter(f"+8190550{i:05d}" for i in range(1, 99999))


def _next_phone() -> str:
    return next(_phone)


def _post_job(client: TestClient, ch: dict[str, str], **over: object) -> str:
    return client.post("/api/v1/jobs", json={**_JOB, **over}, headers=ch).json()["id"]


def _apply(client: TestClient, wh: dict[str, str], job_id: str) -> str:
    resp = client.post(f"/api/v1/jobs/{job_id}/apply", headers=wh)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_apply_then_duplicate_blocked(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", _next_phone(), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", _next_phone(), onboard=_EMPLOYEE)
    job_id = _post_job(client, ch)
    _apply(client, wh, job_id)
    dup = client.post(f"/api/v1/jobs/{job_id}/apply", headers=wh)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "already_applied"


def test_contractor_cannot_apply_worker_cannot_confirm(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", _next_phone(), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", _next_phone(), onboard=_EMPLOYEE)
    job_id = _post_job(client, ch)
    assert client.post(f"/api/v1/jobs/{job_id}/apply", headers=ch).status_code == 403
    app_id = _apply(client, wh, job_id)
    assert client.post(f"/api/v1/applications/{app_id}/confirm", headers=wh).status_code == 403


def test_confirm_employee_routes_to_daylabor_and_records_fee(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", _next_phone(), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", _next_phone(), onboard=_EMPLOYEE)
    job_id = _post_job(client, ch)
    app_id = _apply(client, wh, job_id)

    resp = client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch)
    assert resp.status_code == 201, resp.text
    m = resp.json()
    assert m["status"] == "confirmed"
    assert m["contract_type"] == "employment_daylabor"
    assert m["daily_wage"] == 18000  # snapshot
    assert m["platform_fee"] == 3000  # configured fee
    assert m["fee_status"] == "unpaid"
    # Generated terms are present (default locale ja) and include the snapshot wage.
    assert m["terms"] and "18000" in m["terms"]


def test_confirm_freelance_routes_to_subcontract(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", _next_phone(), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", _next_phone(), onboard=_FREELANCE_INSURED)
    app_id = _apply(client, wh, _post_job(client, ch))
    m = client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch).json()
    assert m["contract_type"] == "subcontract"


def test_uninsured_freelance_confirm_blocked(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", _next_phone(), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", _next_phone(), onboard=_FREELANCE_UNINSURED)
    app_id = _apply(client, wh, _post_job(client, ch))
    resp = client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "freelance_insurance_required"


def test_visa_gate_blocks_confirm_for_non_jp_without_card(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", _next_phone(), onboard=_CONTRACTOR)
    wh, _ = approved_member(
        "worker", _next_phone(),
        onboard={"nationality": "VN", "worker_class": "employee"},
    )
    app_id = _apply(client, wh, _post_job(client, ch))
    resp = client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "visa_card_required"


def test_confirm_twice_is_conflict(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", _next_phone(), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", _next_phone(), onboard=_EMPLOYEE)
    app_id = _apply(client, wh, _post_job(client, ch))
    assert client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch).status_code == 201
    again = client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch)
    assert again.status_code == 409


def test_reject_and_withdraw(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", _next_phone(), onboard=_CONTRACTOR)
    w1, _ = approved_member("worker", _next_phone(), onboard=_EMPLOYEE)
    w2, _ = approved_member("worker", _next_phone(), onboard=_EMPLOYEE)
    job_id = _post_job(client, ch)
    a1 = _apply(client, w1, job_id)
    a2 = _apply(client, w2, job_id)

    assert client.post(f"/api/v1/applications/{a1}/reject", headers=ch).json()["status"] == "rejected"
    assert client.post(f"/api/v1/applications/{a2}/withdraw", headers=w2).json()["status"] == "withdrawn"
    # Rejected application cannot then be confirmed.
    assert client.post(f"/api/v1/applications/{a1}/confirm", headers=ch).status_code == 409


def test_headcount_one_fills_job(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", _next_phone(), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", _next_phone(), onboard=_EMPLOYEE)
    job_id = _post_job(client, ch, headcount=1)
    app_id = _apply(client, wh, job_id)
    client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch)
    assert client.get(f"/api/v1/jobs/{job_id}", headers=ch).json()["status"] == "filled"


def test_matchings_visibility(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", _next_phone(), onboard=_CONTRACTOR)
    wh, _ = approved_member("worker", _next_phone(), onboard=_EMPLOYEE)
    outsider, _ = approved_member("worker", _next_phone(), onboard=_EMPLOYEE)
    app_id = _apply(client, wh, _post_job(client, ch))
    mid = client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch).json()["id"]

    assert len(client.get("/api/v1/matchings/mine", headers=wh).json()) == 1
    assert len(client.get("/api/v1/matchings/mine", headers=ch).json()) == 1
    assert client.get(f"/api/v1/matchings/{mid}", headers=wh).status_code == 200
    assert client.get(f"/api/v1/matchings/{mid}", headers=outsider).status_code == 403
