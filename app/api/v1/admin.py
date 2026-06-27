"""Admin endpoints: vetting queue + approve/reject/suspend (docs/06).

The approve path enforces the visa gate for non-JP workers (docs/08).
Config and matchings admin endpoints are added in later build-order steps.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import admin_user, get_config, get_storage_service
from app.api.v1.onboarding import contractor_out, worker_out
from app.core import errors
from app.core.clock import tokyo_today
from app.core.config import ConfigService
from app.core.storage import StorageService
from app.db.session import get_db
from app.models.contractor_profile import ContractorProfile
from app.models.document import Document
from app.models.enums import UserType
from app.models.user import User
from app.models.worker_profile import WorkerProfile
from app.schemas.admin import RejectIn, SuspendIn, VettingItem, VettingQueueOut
from app.schemas.common import ErrorResponse
from app.schemas.document import DocumentWithUrlOut
from app.schemas.user import UserOut
from app.services import vetting

router = APIRouter(tags=["admin"], dependencies=[Depends(admin_user)])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse}}


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


@router.get("/admin/vetting/queue", response_model=VettingQueueOut)
def vetting_queue(
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> VettingQueueOut:
    items: list[VettingItem] = []
    for user in vetting.vetting_queue(db):
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
        items.append(item)
    return VettingQueueOut(items=items)


@router.post("/admin/users/{user_id}/approve", response_model=UserOut, responses=_NOT_FOUND)
def approve_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    config: ConfigService = Depends(get_config),
) -> UserOut:
    target = _get_target(db, user_id)
    updated = vetting.approve_user(db, target, config=config, today=tokyo_today())
    return UserOut.model_validate(updated)


@router.post("/admin/users/{user_id}/reject", response_model=UserOut, responses=_NOT_FOUND)
def reject_user(
    user_id: uuid.UUID,
    payload: RejectIn,
    db: Session = Depends(get_db),
) -> UserOut:
    target = _get_target(db, user_id)
    updated = vetting.reject_user(db, target, reason=payload.reason)
    return UserOut.model_validate(updated)


@router.post("/admin/users/{user_id}/suspend", response_model=UserOut, responses=_NOT_FOUND)
def suspend_user(
    user_id: uuid.UUID,
    payload: SuspendIn,
    db: Session = Depends(get_db),
) -> UserOut:
    target = _get_target(db, user_id)
    updated = vetting.set_suspended(db, target, suspend=payload.suspend)
    return UserOut.model_validate(updated)
