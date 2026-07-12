"""Matching day-of lifecycle: check-in → complete-request → approve → completed.

All status changes go through the state machine (docs/09). The platform fee was
snapshotted as *owed* at confirm; completion is when it becomes collectable
(``fee_status`` stays ``unpaid`` for manual reconciliation in P1).
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy.orm import Session

from app.core import clock, errors
from app.core.clock import now_utc
from app.core.config import ConfigService
from app.models.enums import MatchingStatus, NotificationType
from app.models.job import Job
from app.models.matching import Matching
from app.models.user import User
from app.services import matchings, notifications
from app.services.state_machine import assert_transition


def _matching_for_worker(db: Session, worker: User, matching_id: uuid.UUID) -> Matching:
    matching = db.get(Matching, matching_id)
    if matching is None:
        raise errors.not_found()
    if matching.worker_id != worker.id:
        raise errors.forbidden()
    return matching


def _matching_for_contractor(db: Session, contractor: User, matching_id: uuid.UUID) -> Matching:
    matching = db.get(Matching, matching_id)
    if matching is None:
        raise errors.not_found()
    job = db.get(Job, matching.job_id)
    if job is None or job.contractor_id != contractor.id:
        raise errors.forbidden()
    return matching


def _contractor_id(db: Session, matching: Matching) -> uuid.UUID | None:
    job = db.get(Job, matching.job_id)
    return job.contractor_id if job else None


def _check_checkin_window(job: Job, config: ConfigService) -> None:
    """Reject check-ins outside the shift window (docs/07).

    Check-in opens ``checkin_open_minutes_before_start`` minutes before the
    job's start (``work_date`` + ``start_time``, Asia/Tokyo) and closes at the
    shift's end (``end_time``; an end at or before the start means the shift
    runs overnight into the next day). ``0``/negative disables the whole check
    — the permissive escape hatch per docs/07.
    """
    open_minutes = config.get_int("checkin_open_minutes_before_start")
    if open_minutes <= 0:
        return
    start = clock.combine_tokyo(job.work_date, job.start_time)
    end = clock.combine_tokyo(job.work_date, job.end_time)
    if job.end_time <= job.start_time:  # overnight shift ends the next day
        end += datetime.timedelta(days=1)
    now = clock.tokyo_now()
    if now < start - datetime.timedelta(minutes=open_minutes):
        raise errors.conflict(
            "checkin_too_early", "error.matching.checkin_too_early", minutes=open_minutes
        )
    if now > end:
        raise errors.conflict(
            "checkin_window_closed", "error.matching.checkin_window_closed"
        )


def check_in(
    db: Session, worker: User, matching_id: uuid.UUID, *, config: ConfigService
) -> Matching:
    matching = _matching_for_worker(db, worker, matching_id)
    assert_transition(matching.status, MatchingStatus.CHECKED_IN)
    job = db.get(Job, matching.job_id)
    if job is not None:
        _check_checkin_window(job, config)
    matching.status = MatchingStatus.CHECKED_IN
    matching.checked_in_at = now_utc()
    contractor_id = _contractor_id(db, matching)
    if contractor_id is not None:
        notifications.notify(
            db, contractor_id, NotificationType.WORKER_CHECKED_IN,
            params={"name": worker.display_name}, link=f"/matchings/{matching.id}",
        )
    db.commit()
    db.refresh(matching)
    return matching


def request_completion(db: Session, worker: User, matching_id: uuid.UUID) -> Matching:
    matching = _matching_for_worker(db, worker, matching_id)
    if matching.status is not MatchingStatus.CHECKED_IN:
        raise errors.conflict("not_checked_in", "error.matching.not_checked_in")
    matching.completion_requested_at = now_utc()
    contractor_id = _contractor_id(db, matching)
    if contractor_id is not None:
        notifications.notify(
            db, contractor_id, NotificationType.COMPLETION_REQUESTED,
            params={"name": worker.display_name}, link=f"/matchings/{matching.id}",
        )
    db.commit()
    db.refresh(matching)
    return matching


def approve_completion(db: Session, contractor: User, matching_id: uuid.UUID) -> Matching:
    matching = _matching_for_contractor(db, contractor, matching_id)
    if matching.completion_requested_at is None:
        raise errors.conflict("completion_not_requested", "error.matching.completion_not_requested")
    assert_transition(matching.status, MatchingStatus.COMPLETED)
    matching.status = MatchingStatus.COMPLETED
    matching.completed_at = now_utc()
    # Fee was set at confirm and remains owed (unpaid) for manual reconciliation.
    job = db.get(Job, matching.job_id)
    notifications.notify(
        db, matching.worker_id, NotificationType.COMPLETION_APPROVED,
        params={"date": job.work_date.isoformat() if job else ""},
        link=f"/matchings/{matching.id}",
    )
    db.commit()
    db.refresh(matching)
    return matching


def cancel(db: Session, user: User, matching_id: uuid.UUID) -> Matching:
    matching = matchings.get_matching(db, user, matching_id)  # participant check
    assert_transition(matching.status, MatchingStatus.CANCELED)
    matching.status = MatchingStatus.CANCELED
    db.commit()
    db.refresh(matching)
    return matching
