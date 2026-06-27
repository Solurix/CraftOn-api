"""reviews — two-way ratings after a completed matching (one per direction)."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPKMixin
from app.models.enums import ReviewDirection, pg_enum


class Review(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("matching_id", "direction", name="uq_reviews_matching_id_direction"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_between_1_and_5"),
    )

    matching_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matchings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    reviewee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[ReviewDirection] = mapped_column(
        pg_enum(ReviewDirection, "review_direction"), nullable=False
    )
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
