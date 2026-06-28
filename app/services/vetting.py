"""Admin vetting services: approve / reject / suspend, enforcing the visa gate."""

from __future__ import annotations

import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import errors
from app.core.config import ConfigService
from app.models.contractor_profile import ContractorProfile
from app.models.document import Document
from app.models.enums import DocReviewStatus, NotificationType, UserStatus, UserType
from app.models.user import User
from app.models.worker_profile import WorkerProfile
from app.services import compliance, notifications


def vetting_queue(db: Session) -> list[User]:
    """Users awaiting review (status pending), oldest first."""
    return list(
        db.scalars(
            select(User)
            .where(User.status == UserStatus.PENDING)
            .where(User.user_type != UserType.ADMIN)
            .order_by(User.created_at.asc())
        ).all()
    )


def list_users(
    db: Session,
    *,
    user_type: UserType | None = None,
    status: UserStatus | None = None,
) -> list[User]:
    """All users (admin overview), newest first, optionally filtered."""
    stmt = select(User)
    if user_type is not None:
        stmt = stmt.where(User.user_type == user_type)
    if status is not None:
        stmt = stmt.where(User.status == status)
    return list(db.scalars(stmt.order_by(User.created_at.desc())).all())


def user_documents(db: Session, user_id: object) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.asc())
        ).all()
    )


def _set_pending_docs(db: Session, user: User, status: DocReviewStatus, note: str | None) -> None:
    for doc in user_documents(db, user.id):
        if doc.review_status is DocReviewStatus.PENDING:
            doc.review_status = status
            if note is not None:
                doc.review_note = note


def approve_user(
    db: Session, target: User, *, config: ConfigService, today: datetime.date
) -> User:
    """Approve a user. For non-JP workers the visa gate must pass (docs/08)."""
    if target.user_type is UserType.WORKER:
        profile = db.get(WorkerProfile, target.id)
        if profile is None:
            raise errors.bad_request("onboarding_incomplete", "error.onboarding.not_completed")
        compliance.check_visa_gate(profile, today=today, config=config)
    elif target.user_type is UserType.CONTRACTOR:
        if db.get(ContractorProfile, target.id) is None:
            raise errors.bad_request("onboarding_incomplete", "error.onboarding.not_completed")

    target.status = UserStatus.APPROVED
    _set_pending_docs(db, target, DocReviewStatus.APPROVED, None)
    notifications.notify(db, target.id, NotificationType.ACCOUNT_APPROVED, link="/")
    db.commit()
    db.refresh(target)
    return target


def maybe_auto_approve(
    db: Session, user: User, *, config: ConfigService, today: datetime.date
) -> bool:
    """Approve ``user`` automatically when the ``auto_approve_users`` flag is on.

    No-op unless the flag is set and the user is still pending. Honors the same
    visa gate as manual approval — a worker who can't pass it (e.g. a non-JP
    worker without a valid visa) is left pending for manual review rather than
    forced through. Returns whether the user ended up approved.
    """
    if user.status is not UserStatus.PENDING:
        return False
    if not config.get_bool("auto_approve_users"):
        return False
    try:
        approve_user(db, user, config=config, today=today)
    except errors.AppError:
        # Gate failed (visa/insurance/no profile) — keep pending, drop any partial
        # transaction so the caller's session stays usable.
        db.rollback()
        return False
    return True


def approve_all_pending(
    db: Session, *, config: ConfigService, today: datetime.date
) -> int:
    """Approve every pending non-admin user that can pass the gate. Returns count.

    Used when an admin flips ``auto_approve_users`` on, to clear the existing
    backlog in one shot. Users that can't be approved (no profile yet, failing
    visa gate) are skipped, not errored.
    """
    approved = 0
    for user in vetting_queue(db):
        try:
            approve_user(db, user, config=config, today=today)
            approved += 1
        except errors.AppError:
            db.rollback()
    return approved


def reject_user(db: Session, target: User, *, reason: str | None) -> User:
    """Reject the submitted documents (user stays pending to re-upload)."""
    _set_pending_docs(db, target, DocReviewStatus.REJECTED, reason)
    notifications.notify(db, target.id, NotificationType.ACCOUNT_REJECTED, link="/profile")
    db.commit()
    db.refresh(target)
    return target


def set_suspended(db: Session, target: User, *, suspend: bool) -> User:
    target.status = UserStatus.SUSPENDED if suspend else UserStatus.APPROVED
    db.commit()
    db.refresh(target)
    return target
