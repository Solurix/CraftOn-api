"""Matching day-of lifecycle: check-in → complete-request → approve → completed.

All status changes go through the state machine (docs/09). The platform fee was
snapshotted as *owed* at confirm; completion is when it becomes collectable
(``fee_status`` stays ``unpaid`` for manual reconciliation in P1).
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core import errors
from app.core.clock import now_utc
from app.models.enums import MatchingStatus
from app.models.job import Job
from app.models.matching import Matching
from app.models.user import User
from app.services import matchings
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


def check_in(db: Session, worker: User, matching_id: uuid.UUID) -> Matching:
    matching = _matching_for_worker(db, worker, matching_id)
    assert_transition(matching.status, MatchingStatus.CHECKED_IN)
    matching.status = MatchingStatus.CHECKED_IN
    matching.checked_in_at = now_utc()
    db.commit()
    db.refresh(matching)
    return matching


def request_completion(db: Session, worker: User, matching_id: uuid.UUID) -> Matching:
    matching = _matching_for_worker(db, worker, matching_id)
    if matching.status is not MatchingStatus.CHECKED_IN:
        raise errors.conflict("not_checked_in", "error.matching.not_checked_in")
    matching.completion_requested_at = now_utc()
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
