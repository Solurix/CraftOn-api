"""Onboarding services: create/complete worker & contractor profiles.

Idempotent ("create/complete"): calling again updates the existing profile.
Status stays ``pending`` until an admin approves (docs/04 §3.1).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import errors
from app.models.contractor_profile import ContractorProfile
from app.models.document import Document
from app.models.enums import UserType
from app.models.user import User
from app.models.worker_profile import WorkerProfile
from app.schemas.contractor import (
    ContractorOnboardingIn,
    ContractorProfileOut,
    ContractorProfileUpdate,
)
from app.schemas.worker import WorkerOnboardingIn, WorkerProfileOut, WorkerProfileUpdate


def worker_out(profile: WorkerProfile, user: User) -> WorkerProfileOut:
    """Build the owner/admin-facing worker profile DTO."""
    return WorkerProfileOut(
        user_id=profile.user_id,
        display_name=user.display_name,
        status=user.status,
        nationality=profile.nationality,
        worker_class=profile.worker_class,
        trades=profile.trades,
        tools=profile.tools,
        has_insurance=profile.has_insurance,
        bio=profile.bio,
        years_experience=profile.years_experience,
        full_name=profile.full_name,
        family_name=profile.family_name,
        given_name=profile.given_name,
        middle_name=profile.middle_name,
        name_kana=profile.name_kana,
        email=profile.email,
        current_employer=profile.current_employer,
        current_employer_public=profile.current_employer_public,
        prefecture=profile.prefecture,
        area=profile.area,
        work_history=profile.work_history,
        qualifications=profile.qualifications,
        skills=profile.skills,
        trust_score=profile.trust_score,
        visa_expiry_date=profile.visa_expiry_date,
        work_restriction=profile.work_restriction,
        residence_card_front_doc_id=profile.residence_card_front_doc_id,
        residence_card_back_doc_id=profile.residence_card_back_doc_id,
    )


def contractor_out(profile: ContractorProfile, user: User) -> ContractorProfileOut:
    """Build the owner/admin-facing contractor profile DTO."""
    return ContractorProfileOut(
        user_id=profile.user_id,
        display_name=user.display_name,
        status=user.status,
        company_name=profile.company_name,
        contact_person=profile.contact_person,
        prefecture=profile.prefecture,
        address=profile.address,
        bio=profile.bio,
        rating=profile.rating,
    )


def _require_role(user: User, expected: UserType) -> None:
    if user.user_type is not expected:
        raise errors.forbidden("error.onboarding.wrong_role")


def _compose_full_name(
    family: str | None, middle: str | None, given: str | None
) -> str | None:
    """Family-first composition (Japanese/Vietnamese convention; middle sits
    between family and given when present): 山田 太郎 / Nguyễn Văn A."""
    parts = [p.strip() for p in (family, middle, given) if p and p.strip()]
    return " ".join(parts) or None


def _validate_owned_doc(db: Session, user: User, doc_id: uuid.UUID | None) -> None:
    if doc_id is None:
        return
    doc = db.get(Document, doc_id)
    if doc is None or doc.user_id != user.id:
        raise errors.bad_request("invalid_document", "error.document.not_owned")


def onboard_worker(db: Session, user: User, payload: WorkerOnboardingIn) -> WorkerProfile:
    _require_role(user, UserType.WORKER)
    _validate_owned_doc(db, user, payload.residence_card_front_doc_id)
    _validate_owned_doc(db, user, payload.residence_card_back_doc_id)

    profile = db.get(WorkerProfile, user.id)
    full_name = (
        _compose_full_name(payload.family_name, payload.middle_name, payload.given_name)
        or payload.full_name
    )
    if payload.display_name:
        user.display_name = payload.display_name
    elif profile is None and full_name:
        # Signup no longer asks for a display name; default it to the worker's
        # name on first onboarding. It stays editable in profile settings.
        user.display_name = full_name

    if profile is None:
        profile = WorkerProfile(user_id=user.id, nationality=payload.nationality,
                                worker_class=payload.worker_class)
        db.add(profile)
    profile.nationality = payload.nationality
    profile.worker_class = payload.worker_class
    profile.trades = payload.trades
    profile.tools = payload.tools
    profile.has_insurance = payload.has_insurance
    profile.bio = payload.bio
    profile.years_experience = payload.years_experience
    profile.full_name = full_name
    profile.family_name = payload.family_name
    profile.given_name = payload.given_name
    profile.middle_name = payload.middle_name
    profile.name_kana = payload.name_kana
    profile.email = payload.email
    profile.current_employer = payload.current_employer
    profile.current_employer_public = payload.current_employer_public
    profile.prefecture = payload.prefecture
    profile.area = payload.area
    profile.work_history = [e.model_dump() for e in payload.work_history]
    profile.qualifications = payload.qualifications
    profile.skills = payload.skills
    # Residence-card links are only overwritten when explicitly sent (same
    # exclude_unset semantics as the PATCH path) — a repeat onboarding POST
    # that omits them must not silently unlink the visa documents (docs/08).
    for doc_field in ("residence_card_front_doc_id", "residence_card_back_doc_id"):
        if doc_field in payload.model_fields_set:
            setattr(profile, doc_field, getattr(payload, doc_field))
    profile.visa_expiry_date = payload.visa_expiry_date
    profile.work_restriction = payload.work_restriction

    db.commit()
    db.refresh(profile)
    return profile


def update_worker(db: Session, user: User, payload: WorkerProfileUpdate) -> WorkerProfile:
    _require_role(user, UserType.WORKER)
    profile = db.get(WorkerProfile, user.id)
    if profile is None:
        raise errors.not_found("error.onboarding.not_completed")

    data = payload.model_dump(exclude_unset=True)
    if "display_name" in data and data["display_name"] is not None:
        user.display_name = data.pop("display_name")
    else:
        data.pop("display_name", None)
    # Ignore explicit nulls for NOT NULL columns (exclude_unset keeps them);
    # setting them would raise an IntegrityError on commit.
    for non_nullable in ("nationality", "worker_class"):
        if data.get(non_nullable) is None:
            data.pop(non_nullable, None)
    for doc_field in ("residence_card_front_doc_id", "residence_card_back_doc_id"):
        if doc_field in data:
            _validate_owned_doc(db, user, data[doc_field])
    for field, value in data.items():
        setattr(profile, field, value)

    # Patching any structured name part recomposes the display full_name
    # (unless the patch set full_name explicitly).
    if {"family_name", "given_name", "middle_name"} & data.keys() and "full_name" not in data:
        profile.full_name = (
            _compose_full_name(
                profile.family_name, profile.middle_name, profile.given_name
            )
            or profile.full_name
        )

    db.commit()
    db.refresh(profile)
    return profile


def onboard_contractor(
    db: Session, user: User, payload: ContractorOnboardingIn
) -> ContractorProfile:
    _require_role(user, UserType.CONTRACTOR)
    profile = db.get(ContractorProfile, user.id)
    if payload.display_name:
        user.display_name = payload.display_name
    elif profile is None:
        # Signup no longer asks for a display name; a contractor's public name
        # defaults to the company name. Editable later in profile settings.
        user.display_name = payload.company_name

    if profile is None:
        profile = ContractorProfile(
            user_id=user.id,
            company_name=payload.company_name,
            contact_person=payload.contact_person,
            prefecture=payload.prefecture,
        )
        db.add(profile)
    profile.company_name = payload.company_name
    profile.contact_person = payload.contact_person
    profile.prefecture = payload.prefecture
    profile.address = payload.address
    profile.bio = payload.bio

    db.commit()
    db.refresh(profile)
    return profile


def update_contractor(
    db: Session, user: User, payload: ContractorProfileUpdate
) -> ContractorProfile:
    _require_role(user, UserType.CONTRACTOR)
    profile = db.get(ContractorProfile, user.id)
    if profile is None:
        raise errors.not_found("error.onboarding.not_completed")

    data = payload.model_dump(exclude_unset=True)
    if "display_name" in data and data["display_name"] is not None:
        user.display_name = data.pop("display_name")
    else:
        data.pop("display_name", None)
    for field, value in data.items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)
    return profile


def get_worker_profile(db: Session, user_id: uuid.UUID) -> WorkerProfile:
    profile = db.get(WorkerProfile, user_id)
    if profile is None:
        raise errors.not_found()
    return profile


def get_contractor_profile(db: Session, user_id: uuid.UUID) -> ContractorProfile:
    profile = db.get(ContractorProfile, user_id)
    if profile is None:
        raise errors.not_found()
    return profile


def display_name_for(db: Session, user_id: uuid.UUID) -> str:
    user = db.get(User, user_id)
    return user.display_name if user else ""


def list_users_by_ids(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, User]:
    if not ids:
        return {}
    rows = db.scalars(select(User).where(User.id.in_(ids))).all()
    return {u.id: u for u in rows}
