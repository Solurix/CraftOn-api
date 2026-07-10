"""worker_profiles — worker-specific data (1:1 with users)."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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
    # Profile detail (Phase 1 display only).
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    years_experience: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    # Extended profile (docs/04 §3.1 onboarding spec). PII (full name, kana,
    # email) is self/admin-only; current employer is shown publicly only when
    # ``current_employer_public`` is set.
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Structured name parts (family/last, given/first, optional middle). The
    # display-oriented ``full_name`` is composed from these on write.
    family_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    given_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    middle_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    name_kana: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_employer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_employer_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    prefecture: Mapped[str | None] = mapped_column(String(64), nullable=True)
    area: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # 職歴: list of {company, trade, years} entries.
    work_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    qualifications: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    skills: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    # Derived display value in Phase 1 (automated penalties are P2).
    trust_score: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, server_default=text("0")
    )

    user: Mapped[User] = relationship(back_populates="worker_profile")
