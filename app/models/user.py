"""users — common account row for every role (worker / contractor / admin)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import UserStatus, UserType, pg_enum

if TYPE_CHECKING:
    from app.models.contractor_profile import ContractorProfile
    from app.models.worker_profile import WorkerProfile


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"

    # Firebase phone identity; the login id. Maps a verified token to this row.
    phone_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    user_type: Mapped[UserType] = mapped_column(pg_enum(UserType, "user_type"), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        pg_enum(UserStatus, "user_status"),
        nullable=False,
        server_default=text(f"'{UserStatus.PENDING.value}'"),
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    preferred_language: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text("'ja'")
    )
    # Optional password for returning logins (OTP still used for new devices).
    # PBKDF2 hash; null until the user sets a password.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    worker_profile: Mapped[WorkerProfile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    contractor_profile: Mapped[ContractorProfile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
