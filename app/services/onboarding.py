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
from app.schemas.contractor import ContractorOnboardingIn, ContractorProfileUpdate
from app.schemas.worker import WorkerOnboardingIn, WorkerProfileUpdate


def _require_role(user: User, expected: UserType) -> None:
    if user.user_type is not expected:
        raise errors.forbidden("error.onboarding.wrong_role")


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

    if payload.display_name:
        user.display_name = payload.display_name

    profile = db.get(WorkerProfile, user.id)
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
    profile.residence_card_front_doc_id = payload.residence_card_front_doc_id
    profile.residence_card_back_doc_id = payload.residence_card_back_doc_id
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
    for doc_field in ("residence_card_front_doc_id", "residence_card_back_doc_id"):
        if doc_field in data:
            _validate_owned_doc(db, user, data[doc_field])
    for field, value in data.items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)
    return profile


def onboard_contractor(
    db: Session, user: User, payload: ContractorOnboardingIn
) -> ContractorProfile:
    _require_role(user, UserType.CONTRACTOR)
    if payload.display_name:
        user.display_name = payload.display_name

    profile = db.get(ContractorProfile, user.id)
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
