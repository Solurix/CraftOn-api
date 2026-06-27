"""Matching read services (lifecycle transitions live in step 6)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import errors
from app.models.enums import UserType
from app.models.job import Job
from app.models.matching import Matching
from app.models.user import User


def is_participant(db: Session, user: User, matching: Matching) -> bool:
    if matching.worker_id == user.id:
        return True
    job = db.get(Job, matching.job_id)
    return job is not None and job.contractor_id == user.id


def get_matching(db: Session, user: User, matching_id: uuid.UUID) -> Matching:
    matching = db.get(Matching, matching_id)
    if matching is None:
        raise errors.not_found()
    if not is_participant(db, user, matching):
        raise errors.forbidden()
    return matching


def list_my_matchings(db: Session, user: User) -> list[Matching]:
    if user.user_type is UserType.WORKER:
        stmt = select(Matching).where(Matching.worker_id == user.id)
    else:  # contractor: matchings for jobs they own
        stmt = (
            select(Matching)
            .join(Job, Matching.job_id == Job.id)
            .where(Job.contractor_id == user.id)
        )
    stmt = stmt.order_by(Matching.created_at.desc())
    return list(db.scalars(stmt).all())
