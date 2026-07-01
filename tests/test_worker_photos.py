"""Public worker portfolio photos: approved viewers see a worker's job photos
(signed read URLs); identity documents are never exposed here."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

Member = Callable[..., tuple[dict[str, str], str]]

_WORKER = {"nationality": "JP", "worker_class": "employee", "trades": ["大工"]}
_CONTRACTOR = {"company_name": "ABC", "contact_person": "S", "prefecture": "Tokyo"}


def _upload(client: TestClient, headers: dict[str, str], doc_type: str) -> None:
    ticket = client.post(
        "/api/v1/documents/upload-url",
        json={"doc_type": doc_type, "content_type": "image/jpeg"},
        headers=headers,
    ).json()
    client.post(
        "/api/v1/documents",
        json={"doc_type": doc_type, "storage_path": ticket["storage_path"]},
        headers=headers,
    )


def test_worker_public_photos_visible_to_approved(
    client: TestClient, approved_member: Member
) -> None:
    wh, wid = approved_member("worker", "+819071110001", onboard=_WORKER)
    _upload(client, wh, "job_photo")
    _upload(client, wh, "photo_id")  # identity doc — must NOT appear publicly

    ch, _ = approved_member("contractor", "+819071110002", onboard=_CONTRACTOR)
    resp = client.get(f"/api/v1/workers/{wid}/photos", headers=ch)
    assert resp.status_code == 200, resp.text
    photos = resp.json()
    assert len(photos) == 1
    assert photos[0]["doc_type"] == "job_photo"
    assert photos[0]["read_url"]


def test_worker_public_photos_requires_approved_viewer(
    client: TestClient, auth_headers: Callable[..., dict[str, str]], approved_member: Member
) -> None:
    _wh, wid = approved_member("worker", "+819071110003", onboard=_WORKER)
    # An unauthenticated request is rejected.
    resp = client.get(f"/api/v1/workers/{wid}/photos")
    assert resp.status_code == 401
