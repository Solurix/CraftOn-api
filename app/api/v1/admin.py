"""Admin endpoints: vetting queue + approve/reject/suspend (docs/06).

The approve path enforces the visa gate for non-JP workers (docs/08).
Config and matchings admin endpoints are added in later build-order steps.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import admin_user, get_config, get_storage_service
from app.core import errors
from app.core.clock import tokyo_today
from app.core.config import AuthMode, ConfigService, get_settings
from app.core.storage import StorageService
from app.db.session import get_db
from app.models.contractor_profile import ContractorProfile
from app.models.document import Document
from app.models.enums import FeeStatus, JobStatus, MatchingStatus, UserStatus, UserType
from app.models.user import User
from app.models.worker_profile import WorkerProfile
from app.schemas.admin import (
    AdminCreateIn,
    ConfigOut,
    ConfigUpdateIn,
    DebugSeedIn,
    DebugSeedOut,
    RejectIn,
    SuspendIn,
    VettingItem,
    VettingQueueOut,
)
from app.schemas.common import RESP_404, ErrorResponse
from app.schemas.document import DocumentWithUrlOut
from app.schemas.job import JobOut
from app.schemas.matching import MatchingOut
from app.schemas.user import UserOut
from app.services import admin_ops, debug_seed, jobs, matchings, vetting
from app.services.onboarding import contractor_out, worker_out

router = APIRouter(tags=["admin"], dependencies=[Depends(admin_user)])


def _doc_out(doc: Document, storage: StorageService) -> DocumentWithUrlOut:
    return DocumentWithUrlOut(
        id=doc.id,
        doc_type=doc.doc_type,
        review_status=doc.review_status,
        review_note=doc.review_note,
        created_at=doc.created_at,
        read_url=storage.read_url(doc.storage_path),
    )


def _get_target(db: Session, user_id: uuid.UUID) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise errors.not_found()
    return target


def _build_user_item(db: Session, user: User, storage: StorageService) -> VettingItem:
    """User + profile + documents — the rich item used by vetting & user lists."""
    docs = [_doc_out(d, storage) for d in vetting.user_documents(db, user.id)]
    item = VettingItem(user=UserOut.model_validate(user), documents=docs)
    if user.user_type is UserType.WORKER:
        wp = db.get(WorkerProfile, user.id)
        if wp is not None:
            item.worker_profile = worker_out(wp, user)
    elif user.user_type is UserType.CONTRACTOR:
        cp = db.get(ContractorProfile, user.id)
        if cp is not None:
            item.contractor_profile = contractor_out(cp, user)
    return item


def _admin_job_out(db: Session, job: object) -> JobOut:
    out = JobOut.model_validate(job)
    out.contractor_company_name = jobs.company_name_for(db, out.contractor_id)
    return out


@router.get("/admin/vetting/queue", response_model=VettingQueueOut)
def vetting_queue(
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> VettingQueueOut:
    items = [_build_user_item(db, u, storage) for u in vetting.vetting_queue(db)]
    return VettingQueueOut(items=items)


@router.get("/admin/users", response_model=VettingQueueOut)
def list_users(
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    user_type: UserType | None = None,
    status: UserStatus | None = None,
) -> VettingQueueOut:
    """All users with profile + documents (full admin visibility)."""
    users = vetting.list_users(db, user_type=user_type, status=status)
    return VettingQueueOut(items=[_build_user_item(db, u, storage) for u in users])


@router.get("/admin/jobs", response_model=list[JobOut])
def list_jobs(
    db: Session = Depends(get_db),
    status: JobStatus | None = None,
) -> list[JobOut]:
    return [_admin_job_out(db, j) for j in admin_ops.list_jobs(db, status=status)]


# -- admins ----------------------------------------------------------------

@router.get("/admin/admins", response_model=list[UserOut])
def list_admins(db: Session = Depends(get_db)) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in admin_ops.list_admins(db)]


@router.post(
    "/admin/admins", response_model=UserOut, status_code=201,
    responses={409: {"model": ErrorResponse}},
)
def create_admin(
    payload: AdminCreateIn,
    db: Session = Depends(get_db),
) -> UserOut:
    admin = admin_ops.create_admin(
        db,
        phone_number=payload.phone_number,
        username=payload.username,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        preferred_language=payload.preferred_language,
    )
    return UserOut.model_validate(admin)


@router.post("/admin/users/{user_id}/approve", response_model=UserOut, responses=RESP_404)
def approve_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    config: ConfigService = Depends(get_config),
) -> UserOut:
    target = _get_target(db, user_id)
    updated = vetting.approve_user(db, target, config=config, today=tokyo_today())
    return UserOut.model_validate(updated)


@router.post("/admin/users/{user_id}/reject", response_model=UserOut, responses=RESP_404)
def reject_user(
    user_id: uuid.UUID,
    payload: RejectIn,
    db: Session = Depends(get_db),
) -> UserOut:
    target = _get_target(db, user_id)
    updated = vetting.reject_user(db, target, reason=payload.reason)
    return UserOut.model_validate(updated)


@router.post("/admin/users/{user_id}/suspend", response_model=UserOut, responses=RESP_404)
def suspend_user(
    user_id: uuid.UUID,
    payload: SuspendIn,
    db: Session = Depends(get_db),
    config: ConfigService = Depends(get_config),
) -> UserOut:
    target = _get_target(db, user_id)
    updated = vetting.set_suspended(
        db, target, suspend=payload.suspend, config=config, today=tokyo_today()
    )
    return UserOut.model_validate(updated)


# -- matchings overview + fee reconciliation -------------------------------

@router.get("/admin/matchings", response_model=list[MatchingOut])
def list_matchings(
    db: Session = Depends(get_db),
    status: MatchingStatus | None = None,
    fee_status: FeeStatus | None = None,
) -> list[MatchingOut]:
    rows = admin_ops.list_matchings(db, status=status, fee_status=fee_status)
    # Enriched with display names for the admin overview (no terms).
    return [matchings.enrich_matching(db, m) for m in rows]


@router.post("/admin/matchings/{matching_id}/mark-fee-paid", response_model=MatchingOut,
             responses=RESP_404)
def mark_fee_paid(
    matching_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> MatchingOut:
    return MatchingOut.model_validate(admin_ops.mark_fee_paid(db, matching_id))


# -- debug tools (non-production only) -------------------------------------

@router.post(
    "/admin/debug/seed", response_model=DebugSeedOut,
    responses={403: {"model": ErrorResponse}},
)
def debug_seed_data(
    payload: DebugSeedIn,
    db: Session = Depends(get_db),
) -> DebugSeedOut:
    # Guard: only available with fake auth (dev/CI), never in production.
    if get_settings().auth_mode is not AuthMode.FAKE:
        raise errors.forbidden("error.admin.debug_disabled")
    counts = debug_seed.seed_random_data(
        db, workers=payload.workers, contractors=payload.contractors, jobs=payload.jobs
    )
    return DebugSeedOut(**counts)


# -- config & flags --------------------------------------------------------

@router.get("/admin/config", response_model=ConfigOut)
def read_config(config: ConfigService = Depends(get_config)) -> ConfigOut:
    return ConfigOut(config=config.all_config())


@router.patch("/admin/config", response_model=ConfigOut, responses=RESP_404)
def update_config(
    payload: ConfigUpdateIn,
    admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
    config: ConfigService = Depends(get_config),
) -> ConfigOut:
    admin_ops.set_config_overrides(db, payload.updates, updated_by=admin.id)
    # Turning auto-approval on clears the existing pending backlog immediately,
    # so the admin doesn't have to approve already-waiting users by hand.
    if "auto_approve_users" in payload.updates and config.get_bool("auto_approve_users"):
        vetting.approve_all_pending(db, config=config, today=tokyo_today())
    return ConfigOut(config=config.all_config())
