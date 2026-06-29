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

    # Phone identity, verified by SMS OTP at registration. One of the login
    # identifiers (alongside username/email) and the canonical key a verified
    # token maps to this row by.
    phone_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    # Login identifiers set at registration. Stored lower-cased so lookup and
    # uniqueness are case-insensitive (see app.core.identifiers.normalize_*).
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
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
    # Password for returning logins (identifier + password, no OTP). PBKDF2 hash;
    # set at registration. Nullable at the column level for legacy/seeded rows.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    worker_profile: Mapped[WorkerProfile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    contractor_profile: Mapped[ContractorProfile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
