"""Onboarding, profiles, documents, and per-role authorization (step 2)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.factories import signup_payload

Headers = Callable[..., dict[str, str]]


def _signup(client: TestClient, headers: dict[str, str], role: str, name: str) -> dict:
    resp = client.post(
        "/api/v1/auth/session",
        json=signup_payload(user_type=role, display_name=name),
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["user"]


def test_worker_onboarding_then_me(client: TestClient, auth_headers: Headers) -> None:
    h = auth_headers("+819011110001")
    _signup(client, h, "worker", "Taro")

    resp = client.post(
        "/api/v1/onboarding/worker",
        json={"nationality": "JP", "worker_class": "employee", "trades": ["大工"]},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["worker_class"] == "employee"
    assert body["trades"] == ["大工"]

    me = client.get("/api/v1/me", headers=h).json()
    assert me["has_worker_profile"] is True
    assert me["worker_profile"]["nationality"] == "JP"


def test_contractor_onboarding(client: TestClient, auth_headers: Headers) -> None:
    h = auth_headers("+819011110002")
    _signup(client, h, "contractor", "Builder")
    resp = client.post(
        "/api/v1/onboarding/contractor",
        json={"company_name": "ABC建設", "contact_person": "Suzuki", "prefecture": "Tokyo"},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["company_name"] == "ABC建設"


def test_wrong_role_onboarding_is_forbidden(client: TestClient, auth_headers: Headers) -> None:
    h = auth_headers("+819011110003")
    _signup(client, h, "contractor", "Builder")
    resp = client.post(
        "/api/v1/onboarding/worker",
        json={"nationality": "JP", "worker_class": "employee"},
        headers=h,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


def test_document_upload_url_and_register(client: TestClient, auth_headers: Headers) -> None:
    h = auth_headers("+819011110004")
    _signup(client, h, "worker", "Taro")

    url_resp = client.post(
        "/api/v1/documents/upload-url",
        json={"doc_type": "photo_id", "content_type": "image/jpeg"},
        headers=h,
    )
    assert url_resp.status_code == 200, url_resp.text
    ticket = url_resp.json()
    assert ticket["method"] == "PUT"
    assert ticket["storage_path"]

    reg = client.post(
        "/api/v1/documents",
        json={"doc_type": "photo_id", "storage_path": ticket["storage_path"]},
        headers=h,
    )
    assert reg.status_code == 201, reg.text
    assert reg.json()["review_status"] == "pending"

    mine = client.get("/api/v1/documents/me", headers=h).json()
    assert len(mine) == 1


def test_documents_require_worker_or_contractor(client: TestClient, auth_headers: Headers) -> None:
    # A user with no token cannot request an upload URL.
    resp = client.post(
        "/api/v1/documents/upload-url", json={"doc_type": "photo_id"}
    )
    assert resp.status_code == 401


def test_document_view_url_owner_and_isolation(
    client: TestClient, auth_headers: Headers
) -> None:
    owner = auth_headers("+819011110010")
    _signup(client, owner, "worker", "Owner")
    ticket = client.post(
        "/api/v1/documents/upload-url",
        json={"doc_type": "job_photo", "content_type": "image/jpeg"},
        headers=owner,
    ).json()
    doc = client.post(
        "/api/v1/documents",
        json={"doc_type": "job_photo", "storage_path": ticket["storage_path"]},
        headers=owner,
    ).json()

    # Owner gets a signed read URL.
    view = client.get(f"/api/v1/documents/{doc['id']}/view-url", headers=owner)
    assert view.status_code == 200, view.text
    assert view.json()["read_url"]

    # A different user cannot view someone else's document.
    other = auth_headers("+819011110011")
    _signup(client, other, "worker", "Other")
    forbidden = client.get(f"/api/v1/documents/{doc['id']}/view-url", headers=other)
    assert forbidden.status_code == 403

    # Unknown id → 404.
    missing = client.get(
        "/api/v1/documents/00000000-0000-0000-0000-000000000000/view-url",
        headers=owner,
    )
    assert missing.status_code == 404


def test_worker_display_name_defaults_to_full_name(
    client: TestClient, auth_headers: Headers
) -> None:
    # Signup no longer collects a display name → the API assigns a provisional
    # one, and first onboarding upgrades it to the worker's real name.
    h = auth_headers("+819011110020")
    _signup(client, h, "worker", "")

    resp = client.post(
        "/api/v1/onboarding/worker",
        json={
            "nationality": "JP",
            "worker_class": "employee",
            "full_name": "山田 太郎",
        },
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["display_name"] == "山田 太郎"

    # Re-onboarding without a display name must not clobber a custom one.
    client.patch("/api/v1/workers/me", json={"display_name": "たろちゃん"}, headers=h)
    again = client.post(
        "/api/v1/onboarding/worker",
        json={"nationality": "JP", "worker_class": "employee", "full_name": "山田 太郎"},
        headers=h,
    )
    assert again.json()["display_name"] == "たろちゃん"


def test_contractor_display_name_defaults_to_company_name(
    client: TestClient, auth_headers: Headers
) -> None:
    h = auth_headers("+819011110021")
    _signup(client, h, "contractor", "")
    resp = client.post(
        "/api/v1/onboarding/contractor",
        json={"company_name": "みらい建築", "contact_person": "Sato", "prefecture": "Tokyo"},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["display_name"] == "みらい建築"


def test_work_history_description_roundtrip(
    client: TestClient, auth_headers: Headers
) -> None:
    h = auth_headers("+819011110022")
    _signup(client, h, "worker", "Taro")
    entry = {
        "company": "山田建設",
        "trade": "大工",
        "years": 3,
        "description": "都内マンションの内装仕上げを担当。",
    }
    resp = client.post(
        "/api/v1/onboarding/worker",
        json={
            "nationality": "JP",
            "worker_class": "employee",
            "work_history": [entry],
        },
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["work_history"] == [entry]


def test_repeat_onboarding_keeps_residence_docs_when_omitted(
    client: TestClient, auth_headers: Headers
) -> None:
    """A repeat POST /onboarding/worker without the doc-id fields must not
    unlink the residence-card documents (they'd silently bypass re-vetting)."""
    h = auth_headers("+819011110024")
    _signup(client, h, "worker", "Binh")

    def _register(doc_type: str) -> str:
        ticket = client.post(
            "/api/v1/documents/upload-url", json={"doc_type": doc_type}, headers=h
        ).json()
        return client.post(
            "/api/v1/documents",
            json={"doc_type": doc_type, "storage_path": ticket["storage_path"]},
            headers=h,
        ).json()["id"]

    front, back = _register("residence_card_front"), _register("residence_card_back")
    first = client.post(
        "/api/v1/onboarding/worker",
        json={
            "nationality": "VN",
            "worker_class": "employee",
            "residence_card_front_doc_id": front,
            "residence_card_back_doc_id": back,
            "visa_expiry_date": "2030-01-01",
        },
        headers=h,
    )
    assert first.status_code == 200, first.text
    assert first.json()["residence_card_front_doc_id"] == front

    # Re-POST without the doc ids (e.g. editing trades) → links are preserved.
    again = client.post(
        "/api/v1/onboarding/worker",
        json={
            "nationality": "VN",
            "worker_class": "employee",
            "trades": ["鳶"],
            "visa_expiry_date": "2030-01-01",
        },
        headers=h,
    )
    assert again.status_code == 200, again.text
    assert again.json()["residence_card_front_doc_id"] == front
    assert again.json()["residence_card_back_doc_id"] == back

    # An explicit null still clears them (exclude_unset, not not-None, semantics).
    cleared = client.post(
        "/api/v1/onboarding/worker",
        json={
            "nationality": "VN",
            "worker_class": "employee",
            "residence_card_front_doc_id": None,
            "residence_card_back_doc_id": None,
        },
        headers=h,
    )
    assert cleared.status_code == 200
    assert cleared.json()["residence_card_front_doc_id"] is None


def test_worker_structured_name_composes_full_name(
    client: TestClient, auth_headers: Headers
) -> None:
    h = auth_headers("+819011110023")
    _signup(client, h, "worker", "")
    resp = client.post(
        "/api/v1/onboarding/worker",
        json={
            "nationality": "VN",
            "worker_class": "employee",
            "visa_expiry_date": "2030-01-01",
            "family_name": "Nguyễn",
            "middle_name": "Văn",
            "given_name": "An",
        },
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Family-first composition, and the display name defaults to it.
    assert body["full_name"] == "Nguyễn Văn An"
    assert body["display_name"] == "Nguyễn Văn An"
    assert (body["family_name"], body["middle_name"], body["given_name"]) == (
        "Nguyễn", "Văn", "An",
    )

    # Patching one part recomposes full_name.
    patched = client.patch(
        "/api/v1/workers/me", json={"given_name": "Bình"}, headers=h
    ).json()
    assert patched["full_name"] == "Nguyễn Văn Bình"
