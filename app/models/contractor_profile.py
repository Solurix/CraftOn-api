"""contractor_profiles — contractor-specific data (1:1 with users)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class ContractorProfile(TimestampMixin, Base):
    __tablename__ = "contractor_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_person: Mapped[str] = mapped_column(String(120), nullable=False)
    prefecture: Mapped[str] = mapped_column(String(64), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Profile detail (Phase 1 display only).
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Derived display value.
    rating: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, server_default=text("0")
    )

    user: Mapped[User] = relationship(back_populates="contractor_profile")
