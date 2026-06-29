"""Admin operations: matchings overview, fee reconciliation, config overrides."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import errors, security
from app.core.config import CONFIG_DEFAULTS
from app.core.identifiers import normalize_email, normalize_username
from app.models.app_config import AppConfig
from app.models.enums import FeeStatus, JobStatus, MatchingStatus, UserStatus, UserType
from app.models.job import Job
from app.models.matching import Matching
from app.models.user import User


def list_admins(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(User.user_type == UserType.ADMIN)
            .order_by(User.created_at.desc())
        ).all()
    )


def create_admin(
    db: Session,
    *,
    phone_number: str,
    username: str,
    email: str,
    password: str,
    display_name: str,
    preferred_language: str = "ja",
) -> User:
    """Create a new, already-approved admin account (admin-only action).

    The admin signs in like any other user: identifier (username/email/phone) +
    password.
    """
    username = normalize_username(username)
    email = normalize_email(email)
    clash = db.scalar(
        select(User).where(
            or_(
                User.phone_number == phone_number,
                User.username == username,
                User.email == email,
            )
        )
    )
    if clash is not None:
        raise errors.conflict("user_exists", "error.admin.user_exists")
    admin = User(
        phone_number=phone_number,
        username=username,
        email=email,
        user_type=UserType.ADMIN,
        status=UserStatus.APPROVED,
        display_name=display_name,
        preferred_language=preferred_language,
        password_hash=security.hash_password(password),
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def list_jobs(db: Session, *, status: JobStatus | None = None) -> list[Job]:
    """All jobs (admin overview), newest first, optionally filtered by status."""
    stmt = select(Job)
    if status is not None:
        stmt = stmt.where(Job.status == status)
    return list(db.scalars(stmt.order_by(Job.created_at.desc())).all())


def list_matchings(
    db: Session,
    *,
    status: MatchingStatus | None = None,
    fee_status: FeeStatus | None = None,
) -> list[Matching]:
    stmt = select(Matching)
    if status is not None:
        stmt = stmt.where(Matching.status == status)
    if fee_status is not None:
        stmt = stmt.where(Matching.fee_status == fee_status)
    stmt = stmt.order_by(Matching.created_at.desc())
    return list(db.scalars(stmt).all())


def mark_fee_paid(db: Session, matching_id: uuid.UUID) -> Matching:
    matching = db.get(Matching, matching_id)
    if matching is None:
        raise errors.not_found()
    matching.fee_status = FeeStatus.PAID
    db.commit()
    db.refresh(matching)
    return matching


def set_config_overrides(
    db: Session, updates: dict[str, Any], *, updated_by: uuid.UUID
) -> None:
    """Upsert runtime config overrides into app_config (admin authority)."""
    unknown = [k for k in updates if k not in CONFIG_DEFAULTS]
    if unknown:
        raise errors.bad_request(
            "unknown_config_key", "error.config.unknown_key", keys=", ".join(unknown)
        )
    for key, value in updates.items():
        row = db.get(AppConfig, key)
        if row is None:
            db.add(AppConfig(key=key, value=value, updated_by=updated_by))
        else:
            row.value = value
            row.updated_by = updated_by
    db.commit()
