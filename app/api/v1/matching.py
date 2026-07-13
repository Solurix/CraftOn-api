"""Application & matching endpoints (docs/06)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import (
    approved_contractor,
    approved_worker,
    get_config,
    require_approved,
)
from app.core.clock import tokyo_today
from app.core.config import ConfigService
from app.db.session import get_db
from app.models.application import Application
from app.models.matching import Matching
from app.models.user import User
from app.models.worker_profile import WorkerProfile
from app.schemas.application import ApplicantOut, ApplicationOut
from app.schemas.common import RESP_403_404_409
from app.schemas.matching import MatchingOut, WorkHistoryOut
from app.services import applications, lifecycle, matchings, terms

router = APIRouter(tags=["matching"])


def _applicant_out(db: Session, app_row: Application) -> ApplicantOut:
    worker = db.get(User, app_row.worker_id)
    profile = db.get(WorkerProfile, app_row.worker_id)
    # An approved worker always has a profile (approval requires onboarding).
    assert profile is not None
    return ApplicantOut(
        id=app_row.id,
        job_id=app_row.job_id,
        worker_id=app_row.worker_id,
        status=app_row.status,
        created_at=app_row.created_at,
        worker_display_name=worker.display_name if worker else "",
        worker_class=profile.worker_class,
        worker_trust_score=profile.trust_score,
    )


def matching_out(db: Session, matching: Matching, *, locale: str) -> MatchingOut:
    out = matchings.enrich_matching(db, matching)
    out.terms = terms.generate_terms(
        contract_type=matching.contract_type,
        worker_name=out.worker_display_name or "",
        company_name=out.contractor_company_name or "",
        work_date=out.work_date.isoformat() if out.work_date else "",
        daily_wage=matching.daily_wage,
        locale=locale,
    )
    return out


# -- applications ----------------------------------------------------------

@router.post("/jobs/{job_id}/apply", response_model=ApplicationOut, status_code=201,
             responses=RESP_403_404_409)
def apply_to_job(
    job_id: uuid.UUID,
    user: User = Depends(approved_worker),
    db: Session = Depends(get_db),
) -> ApplicationOut:
    return ApplicationOut.model_validate(applications.apply_to_job(db, user, job_id))


@router.get("/jobs/{job_id}/applications", response_model=list[ApplicantOut],
            responses=RESP_403_404_409)
def list_applicants(
    job_id: uuid.UUID,
    user: User = Depends(approved_contractor),
    db: Session = Depends(get_db),
) -> list[ApplicantOut]:
    rows = applications.list_applicants(db, user, job_id)
    return [_applicant_out(db, r) for r in rows]


@router.post("/applications/{application_id}/confirm", response_model=MatchingOut,
             status_code=201, responses=RESP_403_404_409)
def confirm_application(
    application_id: uuid.UUID,
    user: User = Depends(approved_contractor),
    db: Session = Depends(get_db),
    config: ConfigService = Depends(get_config),
) -> MatchingOut:
    matching = applications.confirm_application(
        db, user, application_id, config=config, today=tokyo_today()
    )
    return matching_out(db, matching, locale=user.preferred_language)


@router.post("/applications/{application_id}/reject", response_model=ApplicationOut,
             responses=RESP_403_404_409)
def reject_application(
    application_id: uuid.UUID,
    user: User = Depends(approved_contractor),
    db: Session = Depends(get_db),
) -> ApplicationOut:
    return ApplicationOut.model_validate(
        applications.reject_application(db, user, application_id)
    )


@router.post("/applications/{application_id}/withdraw", response_model=ApplicationOut,
             responses=RESP_403_404_409)
def withdraw_application(
    application_id: uuid.UUID,
    user: User = Depends(approved_worker),
    db: Session = Depends(get_db),
) -> ApplicationOut:
    return ApplicationOut.model_validate(
        applications.withdraw_application(db, user, application_id)
    )


@router.get("/applications/mine", response_model=list[ApplicationOut])
def my_applications(
    user: User = Depends(approved_worker),
    db: Session = Depends(get_db),
) -> list[ApplicationOut]:
    return [ApplicationOut.model_validate(a) for a in applications.list_my_applications(db, user)]


# -- matchings -------------------------------------------------------------

@router.get("/matchings/mine", response_model=list[MatchingOut])
def my_matchings(
    user: User = Depends(require_approved),
    db: Session = Depends(get_db),
) -> list[MatchingOut]:
    rows = matchings.list_my_matchings(db, user)
    return [matching_out(db, m, locale=user.preferred_language) for m in rows]


# Literal path declared before the /matchings/{matching_id} catch-all.
@router.get("/matchings/history", response_model=WorkHistoryOut)
def my_work_history(
    user: User = Depends(approved_worker),
    db: Session = Depends(get_db),
) -> WorkHistoryOut:
    rows = matchings.list_worker_history(db, user)
    out = [matching_out(db, m, locale=user.preferred_language) for m in rows]
    return WorkHistoryOut(
        completed_count=len(out),
        total_earned=sum(m.daily_wage for m in out),
        matchings=out,
    )


@router.get("/matchings/{matching_id}", response_model=MatchingOut, responses=RESP_403_404_409)
def get_matching(
    matching_id: uuid.UUID,
    user: User = Depends(require_approved),
    db: Session = Depends(get_db),
) -> MatchingOut:
    matching = matchings.get_matching(db, user, matching_id)
    return matching_out(db, matching, locale=user.preferred_language)


# -- day-of lifecycle ------------------------------------------------------

@router.post("/matchings/{matching_id}/check-in", response_model=MatchingOut,
             responses=RESP_403_404_409)
def check_in(
    matching_id: uuid.UUID,
    user: User = Depends(approved_worker),
    db: Session = Depends(get_db),
    config: ConfigService = Depends(get_config),
) -> MatchingOut:
    matching = lifecycle.check_in(db, user, matching_id, config=config)
    return matching_out(db, matching, locale=user.preferred_language)


@router.post("/matchings/{matching_id}/complete-request", response_model=MatchingOut,
             responses=RESP_403_404_409)
def complete_request(
    matching_id: uuid.UUID,
    user: User = Depends(approved_worker),
    db: Session = Depends(get_db),
) -> MatchingOut:
    matching = lifecycle.request_completion(db, user, matching_id)
    return matching_out(db, matching, locale=user.preferred_language)


@router.post("/matchings/{matching_id}/approve-completion", response_model=MatchingOut,
             responses=RESP_403_404_409)
def approve_completion(
    matching_id: uuid.UUID,
    user: User = Depends(approved_contractor),
    db: Session = Depends(get_db),
) -> MatchingOut:
    matching = lifecycle.approve_completion(db, user, matching_id)
    return matching_out(db, matching, locale=user.preferred_language)


@router.post("/matchings/{matching_id}/cancel", response_model=MatchingOut,
             responses=RESP_403_404_409)
def cancel_matching(
    matching_id: uuid.UUID,
    user: User = Depends(require_approved),
    db: Session = Depends(get_db),
) -> MatchingOut:
    matching = lifecycle.cancel(db, user, matching_id)
    return matching_out(db, matching, locale=user.preferred_language)
