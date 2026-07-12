"""Onboarding & profile endpoints (docs/06)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import contractor_user, get_config, require_approved, worker_user
from app.core.clock import tokyo_today
from app.core.config import ConfigService
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import RESP_404
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
from app.services import onboarding, vetting
from app.services.onboarding import contractor_out, worker_out

router = APIRouter(tags=["onboarding"])


@router.post("/onboarding/worker", response_model=WorkerProfileOut)
def onboard_worker(
    payload: WorkerOnboardingIn,
    user: User = Depends(worker_user),
    db: Session = Depends(get_db),
    config: ConfigService = Depends(get_config),
) -> WorkerProfileOut:
    profile = onboarding.onboard_worker(db, user, payload)
    # Skip the manual vetting step when the admin has enabled auto-approval.
    vetting.maybe_auto_approve(db, user, config=config, today=tokyo_today())
    return worker_out(profile, user)


@router.post("/onboarding/contractor", response_model=ContractorProfileOut)
def onboard_contractor(
    payload: ContractorOnboardingIn,
    user: User = Depends(contractor_user),
    db: Session = Depends(get_db),
    config: ConfigService = Depends(get_config),
) -> ContractorProfileOut:
    profile = onboarding.onboard_contractor(db, user, payload)
    vetting.maybe_auto_approve(db, user, config=config, today=tokyo_today())
    return contractor_out(profile, user)


@router.patch("/workers/me", response_model=WorkerProfileOut, responses=RESP_404)
def update_worker_me(
    payload: WorkerProfileUpdate,
    user: User = Depends(worker_user),
    db: Session = Depends(get_db),
    config: ConfigService = Depends(get_config),
) -> WorkerProfileOut:
    profile = onboarding.update_worker(db, user, payload)
    # A profile fix (e.g. visa data) may make a pending user eligible — retry
    # auto-approval, same as the POST onboarding path.
    vetting.maybe_auto_approve(db, user, config=config, today=tokyo_today())
    return worker_out(profile, user)


@router.patch("/contractors/me", response_model=ContractorProfileOut, responses=RESP_404)
def update_contractor_me(
    payload: ContractorProfileUpdate,
    user: User = Depends(contractor_user),
    db: Session = Depends(get_db),
    config: ConfigService = Depends(get_config),
) -> ContractorProfileOut:
    profile = onboarding.update_contractor(db, user, payload)
    vetting.maybe_auto_approve(db, user, config=config, today=tokyo_today())
    return contractor_out(profile, user)


@router.get("/workers/{user_id}", response_model=WorkerPublicOut, responses=RESP_404)
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


@router.get("/contractors/{user_id}", response_model=ContractorPublicOut, responses=RESP_404)
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
