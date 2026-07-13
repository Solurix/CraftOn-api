"""Matching read services (lifecycle transitions live in step 6)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import errors
from app.models.contractor_profile import ContractorProfile
from app.models.enums import MatchingStatus, UserType
from app.models.job import Job
from app.models.matching import Matching
from app.models.user import User
from app.schemas.matching import MatchingOut


def enrich_matching(db: Session, matching: Matching) -> MatchingOut:
    """``MatchingOut`` enriched with job/worker/company display fields (no terms)."""
    out = MatchingOut.model_validate(matching)
    job = db.get(Job, matching.job_id)
    worker = db.get(User, matching.worker_id)
    company = db.get(ContractorProfile, job.contractor_id) if job else None
    out.contractor_id = job.contractor_id if job else None
    out.worker_display_name = worker.display_name if worker else None
    out.contractor_company_name = company.company_name if company else None
    out.work_date = job.work_date if job else None
    out.prefecture = job.prefecture if job else None
    return out


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


def list_worker_history(db: Session, worker: User) -> list[Matching]:
    """A worker's COMPLETED matchings, most recent work date first (track record)."""
    stmt = (
        select(Matching)
        .join(Job, Matching.job_id == Job.id)
        .where(
            Matching.worker_id == worker.id,
            Matching.status == MatchingStatus.COMPLETED,
        )
        # Most recent work date first; within a day, most recently completed
        # first. The UUID PK is a final, unique tiebreaker for stable ordering.
        .order_by(
            Job.work_date.desc(),
            Matching.completed_at.desc(),
            Matching.id.asc(),
        )
    )
    return list(db.scalars(stmt).all())
