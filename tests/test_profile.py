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
