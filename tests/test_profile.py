"""Profile bio/experience fields: onboarding, public view, and edit (PATCH)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

Member = Callable[..., tuple[dict[str, str], str]]

_CONTRACTOR = {"company_name": "ABC", "contact_person": "S", "prefecture": "Tokyo"}


def test_worker_bio_and_experience_roundtrip(
    client: TestClient, approved_member: Member
) -> None:
    wh, wid = approved_member(
        "worker", "+819077770001",
        onboard={
            "nationality": "JP", "worker_class": "employee", "trades": ["大工"],
            "bio": "10年の経験があります", "years_experience": 10,
        },
    )
    me = client.get("/api/v1/me", headers=wh).json()
    assert me["worker_profile"]["bio"] == "10年の経験があります"
    assert me["worker_profile"]["years_experience"] == 10

    # Visible on the public profile to another approved user.
    viewer, _ = approved_member("contractor", "+819077770002", onboard=_CONTRACTOR)
    pub = client.get(f"/api/v1/workers/{wid}", headers=viewer).json()
    assert pub["bio"] == "10年の経験があります"
    assert pub["years_experience"] == 10

    # Editable via PATCH /workers/me.
    client.patch(
        "/api/v1/workers/me",
        json={"bio": "15年に更新", "years_experience": 15, "tools": ["インパクト"]},
        headers=wh,
    )
    pub2 = client.get(f"/api/v1/workers/{wid}", headers=viewer).json()
    assert pub2["years_experience"] == 15
    assert pub2["bio"] == "15年に更新"
    assert pub2["tools"] == ["インパクト"]


def test_contractor_bio_roundtrip(client: TestClient, approved_member: Member) -> None:
    ch, cid = approved_member(
        "contractor", "+819077770003",
        onboard={**_CONTRACTOR, "bio": "都内中心の工務店です"},
    )
    me = client.get("/api/v1/me", headers=ch).json()
    assert me["contractor_profile"]["bio"] == "都内中心の工務店です"

    viewer, _ = approved_member("worker", "+819077770004",
                                onboard={"nationality": "JP", "worker_class": "employee"})
    pub = client.get(f"/api/v1/contractors/{cid}", headers=viewer).json()
    assert pub["bio"] == "都内中心の工務店です"

    client.patch("/api/v1/contractors/me", json={"bio": "リフォーム専門"}, headers=ch)
    pub2 = client.get(f"/api/v1/contractors/{cid}", headers=viewer).json()
    assert pub2["bio"] == "リフォーム専門"


def test_worker_extended_profile_and_employer_visibility(
    client: TestClient, approved_member: Member
) -> None:
    onboard = {
        "nationality": "JP", "worker_class": "employee", "trades": ["大工"],
        "full_name": "山田 太郎", "name_kana": "ヤマダ タロウ",
        "email": "taro@example.com",
        "current_employer": "山田建設", "current_employer_public": False,
        "prefecture": "Tokyo", "area": "23区",
        "work_history": [
            {"company": "ABC工務店", "trade": "大工", "years": 5},
            {"company": "XYZ建設", "trade": "内装", "years": 3},
        ],
        "qualifications": ["技能士2級"], "skills": ["型枠", "墨出し"],
    }
    wh, wid = approved_member("worker", "+819077771001", onboard=onboard)

    # Self view (PATCH-able /me) keeps the PII + employer.
    me = client.get("/api/v1/me", headers=wh).json()["worker_profile"]
    assert me["full_name"] == "山田 太郎"
    assert me["email"] == "taro@example.com"
    assert me["current_employer"] == "山田建設"
    assert me["work_history"][0] == {
        "company": "ABC工務店", "trade": "大工", "years": 5, "description": ""
    }
    assert me["qualifications"] == ["技能士2級"]
    assert me["skills"] == ["型枠", "墨出し"]

    # Public view: career data is visible; PII (name/email) is NOT; employer is
    # hidden because the worker did not opt to make it public.
    viewer, _ = approved_member("contractor", "+819077771002", onboard=_CONTRACTOR)
    pub = client.get(f"/api/v1/workers/{wid}", headers=viewer).json()
    assert pub["prefecture"] == "Tokyo" and pub["area"] == "23区"
    assert len(pub["work_history"]) == 2
    assert pub["qualifications"] == ["技能士2級"]
    assert pub["current_employer"] is None
    assert "email" not in pub and "full_name" not in pub

    # Opt in to publish the employer → now visible publicly.
    client.patch("/api/v1/workers/me", json={"current_employer_public": True}, headers=wh)
    pub2 = client.get(f"/api/v1/workers/{wid}", headers=viewer).json()
    assert pub2["current_employer"] == "山田建設"


def test_patch_explicit_null_nationality_is_ignored(
    client: TestClient, approved_member: Member
) -> None:
    # Explicit nulls for the NOT NULL nationality/worker_class columns must be
    # dropped (not setattr'd), so the PATCH succeeds instead of 500-ing.
    wh, _ = approved_member(
        "worker", "+819077772001",
        onboard={"nationality": "JP", "worker_class": "employee"},
    )
    resp = client.patch(
        "/api/v1/workers/me",
        json={"nationality": None, "worker_class": None, "bio": "更新"},
        headers=wh,
    )
    assert resp.status_code == 200, resp.text
    me = client.get("/api/v1/me", headers=wh).json()["worker_profile"]
    assert me["nationality"] == "JP" and me["worker_class"] == "employee"
    assert me["bio"] == "更新"


def test_work_history_blank_company_does_not_break_read(
    client: TestClient, approved_member: Member
) -> None:
    # A stored work-history row with a blank company must still serialize on read.
    wh, wid = approved_member(
        "worker", "+819077772002",
        onboard={
            "nationality": "JP", "worker_class": "employee",
            "work_history": [{"company": "", "trade": "大工", "years": 2}],
        },
    )
    me = client.get("/api/v1/me", headers=wh)
    assert me.status_code == 200, me.text
    assert me.json()["worker_profile"]["work_history"][0]["trade"] == "大工"
    viewer, _ = approved_member("contractor", "+819077772003", onboard=_CONTRACTOR)
    assert client.get(f"/api/v1/workers/{wid}", headers=viewer).status_code == 200


def test_bio_and_experience_are_optional(client: TestClient, approved_member: Member) -> None:
    # Onboarding without bio/experience works (permissive defaults).
    wh, wid = approved_member(
        "worker", "+819077770005",
        onboard={"nationality": "JP", "worker_class": "employee"},
    )
    viewer, _ = approved_member("contractor", "+819077770006", onboard=_CONTRACTOR)
    pub = client.get(f"/api/v1/workers/{wid}", headers=viewer).json()
    assert pub["bio"] is None
    assert pub["years_experience"] == 0
