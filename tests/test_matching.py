"""Applications + confirm: routing, gates, fee recording, authZ (step 4)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from tests.factories import CONTRACTOR, EMPLOYEE, Member, apply_to_job, post_job, unique_phone

_FREELANCE_INSURED = {
    "nationality": "JP", "worker_class": "freelance", "has_insurance": True,
}
_FREELANCE_UNINSURED = {
    "nationality": "JP", "worker_class": "freelance", "has_insurance": False,
}


def _post_job(client: TestClient, ch: dict[str, str], **over: Any) -> str:
    # This file's jobs default to headcount=2 (several tests need an unfilled job).
    return post_job(client, ch, **{"headcount": 2, **over})


def test_apply_then_duplicate_blocked(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    wh, _ = approved_member("worker", unique_phone(), onboard=EMPLOYEE)
    job_id = _post_job(client, ch)
    apply_to_job(client, wh, job_id)
    dup = client.post(f"/api/v1/jobs/{job_id}/apply", headers=wh)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "already_applied"


def test_contractor_cannot_apply_worker_cannot_confirm(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    wh, _ = approved_member("worker", unique_phone(), onboard=EMPLOYEE)
    job_id = _post_job(client, ch)
    assert client.post(f"/api/v1/jobs/{job_id}/apply", headers=ch).status_code == 403
    app_id = apply_to_job(client, wh, job_id)
    assert client.post(f"/api/v1/applications/{app_id}/confirm", headers=wh).status_code == 403


def test_confirm_employee_routes_to_daylabor_and_records_fee(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    wh, _ = approved_member("worker", unique_phone(), onboard=EMPLOYEE)
    job_id = _post_job(client, ch)
    app_id = apply_to_job(client, wh, job_id)

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
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    wh, _ = approved_member("worker", unique_phone(), onboard=_FREELANCE_INSURED)
    app_id = apply_to_job(client, wh, _post_job(client, ch))
    m = client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch).json()
    assert m["contract_type"] == "subcontract"


def test_uninsured_freelance_confirm_blocked(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    wh, _ = approved_member("worker", unique_phone(), onboard=_FREELANCE_UNINSURED)
    app_id = apply_to_job(client, wh, _post_job(client, ch))
    resp = client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "freelance_insurance_required"


def test_visa_gate_blocks_confirm_for_non_jp_without_card(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    wh, _ = approved_member(
        "worker", unique_phone(),
        onboard={"nationality": "VN", "worker_class": "employee"},
    )
    app_id = apply_to_job(client, wh, _post_job(client, ch))
    resp = client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "visa_card_required"


def test_confirm_twice_is_conflict(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    wh, _ = approved_member("worker", unique_phone(), onboard=EMPLOYEE)
    app_id = apply_to_job(client, wh, _post_job(client, ch))
    assert client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch).status_code == 201
    again = client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch)
    assert again.status_code == 409


def test_reject_and_withdraw(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    w1, _ = approved_member("worker", unique_phone(), onboard=EMPLOYEE)
    w2, _ = approved_member("worker", unique_phone(), onboard=EMPLOYEE)
    job_id = _post_job(client, ch)
    a1 = apply_to_job(client, w1, job_id)
    a2 = apply_to_job(client, w2, job_id)

    assert client.post(f"/api/v1/applications/{a1}/reject", headers=ch).json()["status"] == "rejected"
    assert client.post(f"/api/v1/applications/{a2}/withdraw", headers=w2).json()["status"] == "withdrawn"
    # Rejected application cannot then be confirmed.
    assert client.post(f"/api/v1/applications/{a1}/confirm", headers=ch).status_code == 409


def test_headcount_one_fills_job(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    wh, _ = approved_member("worker", unique_phone(), onboard=EMPLOYEE)
    job_id = _post_job(client, ch, headcount=1)
    app_id = apply_to_job(client, wh, job_id)
    client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch)
    assert client.get(f"/api/v1/jobs/{job_id}", headers=ch).json()["status"] == "filled"


def test_headcount_two_fills_only_after_second_confirm(
    client: TestClient, approved_member: Member
) -> None:
    # A headcount=2 job must stay open after the first confirmation and only
    # flip to filled once the second worker is confirmed.
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    w1, _ = approved_member("worker", unique_phone(), onboard=EMPLOYEE)
    w2, _ = approved_member("worker", unique_phone(), onboard=EMPLOYEE)
    job_id = _post_job(client, ch, headcount=2)
    a1 = apply_to_job(client, w1, job_id)
    a2 = apply_to_job(client, w2, job_id)

    client.post(f"/api/v1/applications/{a1}/confirm", headers=ch)
    assert client.get(f"/api/v1/jobs/{job_id}", headers=ch).json()["status"] == "open"

    client.post(f"/api/v1/applications/{a2}/confirm", headers=ch)
    assert client.get(f"/api/v1/jobs/{job_id}", headers=ch).json()["status"] == "filled"


def test_matchings_visibility(client: TestClient, approved_member: Member) -> None:
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    wh, _ = approved_member("worker", unique_phone(), onboard=EMPLOYEE)
    outsider, _ = approved_member("worker", unique_phone(), onboard=EMPLOYEE)
    app_id = apply_to_job(client, wh, _post_job(client, ch))
    mid = client.post(f"/api/v1/applications/{app_id}/confirm", headers=ch).json()["id"]

    assert len(client.get("/api/v1/matchings/mine", headers=wh).json()) == 1
    assert len(client.get("/api/v1/matchings/mine", headers=ch).json()) == 1
    assert client.get(f"/api/v1/matchings/{mid}", headers=wh).status_code == 200
    assert client.get(f"/api/v1/matchings/{mid}", headers=outsider).status_code == 403
