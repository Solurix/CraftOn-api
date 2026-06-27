"""documents — uploaded IDs / residence cards / qualifications / job photos.

The image bytes live in Cloud Storage (``storage_path``); we serve them via
signed URLs and prefer storing derived fields over hoarding images (docs/08).
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPKMixin
from app.models.enums import DocReviewStatus, DocType, pg_enum


class Document(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "documents"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doc_type: Mapped[DocType] = mapped_column(pg_enum(DocType, "doc_type"), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    review_status: Mapped[DocReviewStatus] = mapped_column(
        pg_enum(DocReviewStatus, "doc_review_status"),
        nullable=False,
        server_default=text(f"'{DocReviewStatus.PENDING.value}'"),
    )
    review_note: Mapped[str | None] = mapped_column(String(512), nullable=True)
