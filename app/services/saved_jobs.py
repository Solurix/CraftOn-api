"""Saved-jobs services: a worker bookmarks jobs to revisit/apply later.

Saving is idempotent (a second save is a no-op); unsaving a job that isn't saved
is also a no-op. The unique (worker_id, job_id) constraint backs idempotency.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import errors
from app.models.job import Job
from app.models.saved_job import SavedJob
from app.models.user import User


def _saved_row(db: Session, worker: User, job_id: uuid.UUID) -> SavedJob | None:
    return db.scalar(
        select(SavedJob).where(
            SavedJob.worker_id == worker.id, SavedJob.job_id == job_id
        )
    )


def save_job(db: Session, worker: User, job_id: uuid.UUID) -> None:
    # 404 on an unknown job so the client can't silently bookmark nothing.
    if db.get(Job, job_id) is None:
        raise errors.not_found()
    if _saved_row(db, worker, job_id) is not None:
        return
    db.add(SavedJob(worker_id=worker.id, job_id=job_id))
    try:
        db.commit()
    except IntegrityError:
        # Lost a concurrent save race (same worker+job): the unique constraint
        # rejected the duplicate. The bookmark now exists, so this is a no-op.
        db.rollback()


def unsave_job(db: Session, worker: User, job_id: uuid.UUID) -> None:
    row = _saved_row(db, worker, job_id)
    if row is not None:
        db.delete(row)
        db.commit()


def list_saved_jobs(db: Session, worker: User) -> list[Job]:
    """The worker's saved jobs (most-recently-saved first), any job status."""
    stmt = (
        select(Job)
        .join(SavedJob, SavedJob.job_id == Job.id)
        .where(SavedJob.worker_id == worker.id)
        .order_by(SavedJob.created_at.desc())
    )
    return list(db.scalars(stmt).all())


def saved_job_ids(db: Session, worker: User) -> list[uuid.UUID]:
    """Just the saved job ids — lets the jobs list render the toggle state cheaply."""
    return list(
        db.scalars(
            select(SavedJob.job_id).where(SavedJob.worker_id == worker.id)
        ).all()
    )
