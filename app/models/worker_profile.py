"""worker_profiles — worker-specific data (1:1 with users)."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import WorkerClass, pg_enum

if TYPE_CHECKING:
    from app.models.user import User


class WorkerProfile(TimestampMixin, Base):
    __tablename__ = "worker_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    nationality: Mapped[str] = mapped_column(String(2), nullable=False)  # ISO-ish: JP, VN, ID
    worker_class: Mapped[WorkerClass] = mapped_column(
        pg_enum(WorkerClass, "worker_class"), nullable=False
    )

    # Residence-card images (required if non-JP) — FK to documents. Visa gate (docs/08).
    residence_card_front_doc_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    residence_card_back_doc_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    visa_expiry_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    # (P2) visa type / 28h-limit flags; logic lands in Phase 2.
    work_restriction: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 一人親方労災 proof present; required for `freelance` to be confirmable (config gate).
    has_insurance: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    trades: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    tools: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    # Derived display value in Phase 1 (automated penalties are P2).
    trust_score: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, server_default=text("0")
    )

    user: Mapped[User] = relationship(back_populates="worker_profile")
