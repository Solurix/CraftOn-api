"""Job posting, search, lifecycle, config-driven gates, and authZ (step 3)."""

from __future__ import annotations

import datetime
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.core import clock

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


def test_search_wage_and_date_range_and_sort(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", "+819033339001", onboard=_CONTRACTOR_ONBOARD)
    # Three open jobs with distinct wages and dates.
    client.post("/api/v1/jobs", json={**_JOB, "daily_wage": 12000, "work_date": "2026-07-01"}, headers=ch)
    client.post("/api/v1/jobs", json={**_JOB, "daily_wage": 18000, "work_date": "2026-07-05"}, headers=ch)
    client.post("/api/v1/jobs", json={**_JOB, "daily_wage": 25000, "work_date": "2026-07-10"}, headers=ch)

    wh, _ = approved_member("worker", "+819033339002", onboard=_WORKER_ONBOARD)

    # Wage range (inclusive).
    wage = client.get("/api/v1/jobs", params={"wage_min": 15000, "wage_max": 20000}, headers=wh).json()
    assert [j["daily_wage"] for j in wage] == [18000]

    # Date range (inclusive).
    dated = client.get(
        "/api/v1/jobs", params={"date_from": "2026-07-04", "date_to": "2026-07-10"}, headers=wh
    ).json()
    assert {j["work_date"] for j in dated} == {"2026-07-05", "2026-07-10"}

    # Sort by wage, high to low.
    high = client.get("/api/v1/jobs", params={"sort": "wage_high"}, headers=wh).json()
    assert [j["daily_wage"] for j in high] == [25000, 18000, 12000]
    low = client.get("/api/v1/jobs", params={"sort": "wage_low"}, headers=wh).json()
    assert [j["daily_wage"] for j in low] == [12000, 18000, 25000]


def test_search_invalid_sort_rejected(
    client: TestClient, approved_member: Member
) -> None:
    wh, _ = approved_member("worker", "+819033339003", onboard=_WORKER_ONBOARD)
    assert client.get("/api/v1/jobs", params={"sort": "bogus"}, headers=wh).status_code == 422


def test_search_pagination_is_stable_across_ties(
    client: TestClient, approved_member: Member
) -> None:
    # Two jobs tied on the sort columns (same wage + work_date) must paginate
    # deterministically: limit=1 across offsets returns each exactly once.
    ch, _ = approved_member("contractor", "+819033339004", onboard=_CONTRACTOR_ONBOARD)
    client.post("/api/v1/jobs", json={**_JOB, "daily_wage": 20000, "work_date": "2026-09-01"}, headers=ch)
    client.post("/api/v1/jobs", json={**_JOB, "daily_wage": 20000, "work_date": "2026-09-01"}, headers=ch)

    wh, _ = approved_member("worker", "+819033339005", onboard=_WORKER_ONBOARD)
    p = {"sort": "wage_high", "limit": 1}
    page1 = client.get("/api/v1/jobs", params={**p, "offset": 0}, headers=wh).json()
    page2 = client.get("/api/v1/jobs", params={**p, "offset": 1}, headers=wh).json()
    assert len(page1) == 1 and len(page2) == 1
    assert page1[0]["id"] != page2[0]["id"]  # disjoint pages, no row repeated/skipped


def test_invalid_times_rejected(client: TestClient, approved_member: Member) -> None:
    # end == start is ambiguous (0h vs 24h) → rejected. end < start is a valid
    # NIGHT SHIFT (ends next day) — covered by test_night_shift_job below.
    h, _ = approved_member("contractor", "+819033330005", onboard=_CONTRACTOR_ONBOARD)
    resp = client.post(
        "/api/v1/jobs",
        json={**_JOB, "start_time": "17:00:00", "end_time": "17:00:00"},
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
    # Far-future work date so the edit-cutoff window (tests/test_job_edit_rules.py)
    # never interferes with the ownership checks under test here.
    future = (clock.tokyo_today() + datetime.timedelta(days=30)).isoformat()
    job_id = client.post(
        "/api/v1/jobs", json={**_JOB, "work_date": future}, headers=owner
    ).json()["id"]

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


def test_night_shift_job_allows_end_before_start(
    client: TestClient, approved_member
) -> None:
    # 21:00–05:00 (next day) — the UI enters this as 21:00–29:00. Only an
    # exactly-equal start/end pair is rejected (ambiguous 0h vs 24h).
    ch, _ = approved_member(
        "contractor", "+819055500001",
        onboard={"company_name": "夜間工事", "contact_person": "S", "prefecture": "Tokyo"},
    )
    ok = client.post(
        "/api/v1/jobs",
        json={
            "trades": ["解体"], "work_date": "2026-08-01",
            "start_time": "21:00:00", "end_time": "05:00:00",
            "prefecture": "Tokyo", "daily_wage": 25000, "headcount": 2,
        },
        headers=ch,
    )
    assert ok.status_code in (200, 201), ok.text
    body = ok.json()
    assert body["start_time"] == "21:00:00" and body["end_time"] == "05:00:00"

    equal = client.post(
        "/api/v1/jobs",
        json={
            "trades": ["解体"], "work_date": "2026-08-01",
            "start_time": "08:00:00", "end_time": "08:00:00",
            "prefecture": "Tokyo", "daily_wage": 25000,
        },
        headers=ch,
    )
    assert equal.status_code == 422


def test_job_photos_attach_and_public_read(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", "+819055500002", onboard=_CONTRACTOR_ONBOARD)
    # Upload one photo document, reuse it on the posting.
    ticket = client.post(
        "/api/v1/documents/upload-url",
        json={"doc_type": "job_photo", "content_type": "image/jpeg"},
        headers=ch,
    ).json()
    doc = client.post(
        "/api/v1/documents",
        json={"doc_type": "job_photo", "storage_path": ticket["storage_path"]},
        headers=ch,
    ).json()

    created = client.post(
        "/api/v1/jobs", json={**_JOB, "photo_doc_ids": [doc["id"]]}, headers=ch
    )
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["photo_doc_ids"] == [doc["id"]]

    # Another approved user (a worker) can read the photo URLs via the job…
    wh, _ = approved_member(
        "worker", "+819055500003",
        onboard={"nationality": "JP", "worker_class": "employee"},
    )
    photos = client.get(f"/api/v1/jobs/{job['id']}/photos", headers=wh)
    assert photos.status_code == 200, photos.text
    assert photos.json()[0]["document_id"] == doc["id"]
    assert photos.json()[0]["read_url"]
    # …but NOT the private document view-url endpoint.
    assert (
        client.get(f"/api/v1/documents/{doc['id']}/view-url", headers=wh).status_code
        == 403
    )


def test_job_photos_must_be_own_job_photo_docs(
    client: TestClient, approved_member: Member
) -> None:
    ch, _ = approved_member("contractor", "+819055500004", onboard=_CONTRACTOR_ONBOARD)
    other, _ = approved_member("contractor", "+819055500005", onboard=_CONTRACTOR_ONBOARD)
    ticket = client.post(
        "/api/v1/documents/upload-url",
        json={"doc_type": "job_photo", "content_type": "image/jpeg"},
        headers=other,
    ).json()
    foreign = client.post(
        "/api/v1/documents",
        json={"doc_type": "job_photo", "storage_path": ticket["storage_path"]},
        headers=other,
    ).json()
    resp = client.post(
        "/api/v1/jobs", json={**_JOB, "photo_doc_ids": [foreign["id"]]}, headers=ch
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_photo"


def test_job_photo_registers_approved_but_vetting_docs_stay_pending(
    client: TestClient, approved_member: Member
) -> None:
    """Work photos are post-moderated — the only approval is per-account
    (vetting), so they're born `approved`. Identity docs still start pending."""
    ch, _ = approved_member(
        "contractor", "+819055500099", onboard=_CONTRACTOR_ONBOARD
    )
    ticket = client.post(
        "/api/v1/documents/upload-url",
        json={"doc_type": "job_photo", "content_type": "image/jpeg"},
        headers=ch,
    ).json()
    photo = client.post(
        "/api/v1/documents",
        json={"doc_type": "job_photo", "storage_path": ticket["storage_path"]},
        headers=ch,
    ).json()
    assert photo["review_status"] == "approved"

    ticket = client.post(
        "/api/v1/documents/upload-url",
        json={"doc_type": "residence_card_front", "content_type": "image/jpeg"},
        headers=ch,
    ).json()
    card = client.post(
        "/api/v1/documents",
        json={
            "doc_type": "residence_card_front",
            "storage_path": ticket["storage_path"],
        },
        headers=ch,
    ).json()
    assert card["review_status"] == "pending"
