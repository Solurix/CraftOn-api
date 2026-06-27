"""Review schemas."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ReviewDirection


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)
    tags: list[str] = Field(default_factory=list)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    matching_id: uuid.UUID
    reviewer_id: uuid.UUID
    reviewee_id: uuid.UUID
    direction: ReviewDirection
    rating: int
    comment: str | None
    tags: list[str]
    created_at: datetime.datetime
