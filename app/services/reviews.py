"""Review services: two-way reviews after completion + derived trust display.

One review per direction per matching, only by participants, only after the
matching is ``completed``. The reviewee's display value (worker ``trust_score`` /
contractor ``rating``) is recomputed as the average of their received ratings —
a derived display number in Phase 1 (automated penalties are P2).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import errors
from app.models.contractor_profile import ContractorProfile
from app.models.enums import MatchingStatus, NotificationType, ReviewDirection
from app.models.job import Job
from app.models.review import Review
from app.models.user import User
from app.models.worker_profile import WorkerProfile
from app.services import matchings, notifications


def _avg_rating(db: Session, reviewee_id: uuid.UUID, direction: ReviewDirection) -> Decimal:
    avg = db.scalar(
        select(func.avg(Review.rating)).where(
            Review.reviewee_id == reviewee_id, Review.direction == direction
        )
    )
    return Decimal(avg).quantize(Decimal("0.01")) if avg is not None else Decimal("0")


def _recompute_display(db: Session, reviewee_id: uuid.UUID, direction: ReviewDirection) -> None:
    if direction is ReviewDirection.CONTRACTOR_TO_WORKER:
        profile = db.get(WorkerProfile, reviewee_id)
        if profile is not None:
            profile.trust_score = _avg_rating(db, reviewee_id, direction)
    else:
        contractor = db.get(ContractorProfile, reviewee_id)
        if contractor is not None:
            contractor.rating = _avg_rating(db, reviewee_id, direction)


def create_review(
    db: Session,
    user: User,
    matching_id: uuid.UUID,
    *,
    rating: int,
    comment: str | None,
    tags: list[str],
) -> Review:
    matching = matchings.get_matching(db, user, matching_id)  # participant check
    if matching.status is not MatchingStatus.COMPLETED:
        raise errors.conflict("review_not_allowed", "error.review.not_completed")

    job = db.get(Job, matching.job_id)
    assert job is not None
    if matching.worker_id == user.id:
        direction = ReviewDirection.WORKER_TO_CONTRACTOR
        reviewee_id = job.contractor_id
    else:
        direction = ReviewDirection.CONTRACTOR_TO_WORKER
        reviewee_id = matching.worker_id

    existing = db.scalar(
        select(Review).where(
            Review.matching_id == matching_id, Review.direction == direction
        )
    )
    if existing is not None:
        raise errors.conflict("already_reviewed", "error.review.already_reviewed")

    review = Review(
        matching_id=matching_id,
        reviewer_id=user.id,
        reviewee_id=reviewee_id,
        direction=direction,
        rating=rating,
        comment=comment,
        tags=tags,
    )
    db.add(review)
    db.flush()  # ensure the new row is counted in the average
    _recompute_display(db, reviewee_id, direction)
    notifications.notify(
        db,
        reviewee_id,
        NotificationType.REVIEW_RECEIVED,
        params={"rating": rating},
        link=f"/matchings/{matching_id}",
    )
    db.commit()
    db.refresh(review)
    return review


def list_reviews_for(
    db: Session, reviewee_id: uuid.UUID, direction: ReviewDirection
) -> list[Review]:
    return list(
        db.scalars(
            select(Review)
            .where(Review.reviewee_id == reviewee_id, Review.direction == direction)
            .order_by(Review.created_at.desc())
        ).all()
    )
