"""Review endpoints (docs/06)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_approved
from app.db.session import get_db
from app.models.enums import ReviewDirection
from app.models.user import User
from app.schemas.common import RESP_403_404_409
from app.schemas.review import ReviewCreate, ReviewOut
from app.services import reviews

router = APIRouter(tags=["reviews"])


@router.post("/matchings/{matching_id}/reviews", response_model=ReviewOut,
             status_code=201, responses=RESP_403_404_409)
def create_review(
    matching_id: uuid.UUID,
    payload: ReviewCreate,
    user: User = Depends(require_approved),
    db: Session = Depends(get_db),
) -> ReviewOut:
    review = reviews.create_review(
        db, user, matching_id,
        rating=payload.rating, comment=payload.comment, tags=payload.tags,
    )
    return ReviewOut.model_validate(review)


@router.get("/workers/{user_id}/reviews", response_model=list[ReviewOut])
def worker_reviews(
    user_id: uuid.UUID,
    _viewer: User = Depends(require_approved),
    db: Session = Depends(get_db),
) -> list[ReviewOut]:
    rows = reviews.list_reviews_for(db, user_id, ReviewDirection.CONTRACTOR_TO_WORKER)
    return [ReviewOut.model_validate(r) for r in rows]


@router.get("/contractors/{user_id}/reviews", response_model=list[ReviewOut])
def contractor_reviews(
    user_id: uuid.UUID,
    _viewer: User = Depends(require_approved),
    db: Session = Depends(get_db),
) -> list[ReviewOut]:
    rows = reviews.list_reviews_for(db, user_id, ReviewDirection.WORKER_TO_CONTRACTOR)
    return [ReviewOut.model_validate(r) for r in rows]
