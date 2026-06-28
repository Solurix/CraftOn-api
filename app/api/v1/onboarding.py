"""Onboarding & profile endpoints (docs/06)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import contractor_user, require_approved, worker_user
from app.db.session import get_db
from app.models.contractor_profile import ContractorProfile
from app.models.user import User
from app.models.worker_profile import WorkerProfile
from app.schemas.common import ErrorResponse
from app.schemas.contractor import (
    ContractorOnboardingIn,
    ContractorProfileOut,
    ContractorProfileUpdate,
    ContractorPublicOut,
)
from app.schemas.worker import (
    WorkerOnboardingIn,
    WorkerProfileOut,
    WorkerProfileUpdate,
    WorkerPublicOut,
)
from app.services import onboarding

router = APIRouter(tags=["onboarding"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse}}


def worker_out(profile: WorkerProfile, user: User) -> WorkerProfileOut:
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


@router.post("/onboarding/worker", response_model=WorkerProfileOut)
def onboard_worker(
    payload: WorkerOnboardingIn,
    user: User = Depends(worker_user),
    db: Session = Depends(get_db),
) -> WorkerProfileOut:
    profile = onboarding.onboard_worker(db, user, payload)
    return worker_out(profile, user)


@router.post("/onboarding/contractor", response_model=ContractorProfileOut)
def onboard_contractor(
    payload: ContractorOnboardingIn,
    user: User = Depends(contractor_user),
    db: Session = Depends(get_db),
) -> ContractorProfileOut:
    profile = onboarding.onboard_contractor(db, user, payload)
    return contractor_out(profile, user)


@router.patch("/workers/me", response_model=WorkerProfileOut, responses=_NOT_FOUND)
def update_worker_me(
    payload: WorkerProfileUpdate,
    user: User = Depends(worker_user),
    db: Session = Depends(get_db),
) -> WorkerProfileOut:
    profile = onboarding.update_worker(db, user, payload)
    return worker_out(profile, user)


@router.patch("/contractors/me", response_model=ContractorProfileOut, responses=_NOT_FOUND)
def update_contractor_me(
    payload: ContractorProfileUpdate,
    user: User = Depends(contractor_user),
    db: Session = Depends(get_db),
) -> ContractorProfileOut:
    profile = onboarding.update_contractor(db, user, payload)
    return contractor_out(profile, user)


@router.get("/workers/{user_id}", response_model=WorkerPublicOut, responses=_NOT_FOUND)
def get_worker(
    user_id: uuid.UUID,
    _viewer: User = Depends(require_approved),
    db: Session = Depends(get_db),
) -> WorkerPublicOut:
    profile = onboarding.get_worker_profile(db, user_id)
    return WorkerPublicOut(
        user_id=profile.user_id,
        display_name=onboarding.display_name_for(db, profile.user_id),
        worker_class=profile.worker_class,
        trades=profile.trades,
        tools=profile.tools,
        bio=profile.bio,
        years_experience=profile.years_experience,
        prefecture=profile.prefecture,
        area=profile.area,
        # Current employer is shown publicly only if the worker opted in.
        current_employer=(
            profile.current_employer if profile.current_employer_public else None
        ),
        work_history=profile.work_history,
        qualifications=profile.qualifications,
        skills=profile.skills,
        trust_score=profile.trust_score,
    )


@router.get("/contractors/{user_id}", response_model=ContractorPublicOut, responses=_NOT_FOUND)
def get_contractor(
    user_id: uuid.UUID,
    _viewer: User = Depends(require_approved),
    db: Session = Depends(get_db),
) -> ContractorPublicOut:
    profile = onboarding.get_contractor_profile(db, user_id)
    return ContractorPublicOut(
        user_id=profile.user_id,
        display_name=onboarding.display_name_for(db, profile.user_id),
        company_name=profile.company_name,
        prefecture=profile.prefecture,
        bio=profile.bio,
        rating=profile.rating,
    )
