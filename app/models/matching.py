"""matchings — a confirmed application; the day-of lifecycle + fee record.

State machine (enforced in services, see docs/09):
    confirmed → checked_in → completed
    confirmed/checked_in → canceled | noshow
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import ContractType, FeeStatus, MatchingStatus, pg_enum


class Matching(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "matchings"
    __table_args__ = (
        Index("ix_matchings_worker_id_status", "worker_id", "status"),
        Index("ix_matchings_job_id", "job_id"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    worker_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[MatchingStatus] = mapped_column(
        pg_enum(MatchingStatus, "matching_status"), nullable=False
    )
    # Recorded at confirm time from worker_class (employee→employment, freelance→subcontract).
    contract_type: Mapped[ContractType] = mapped_column(
        pg_enum(ContractType, "contract_type"), nullable=False
    )
    daily_wage: Mapped[int] = mapped_column(Integer, nullable=False)  # JPY snapshot
    platform_fee: Mapped[int] = mapped_column(Integer, nullable=False)  # JPY (config var)
    fee_status: Mapped[FeeStatus] = mapped_column(
        pg_enum(FeeStatus, "fee_status"),
        nullable=False,
        server_default=text(f"'{FeeStatus.UNPAID.value}'"),
    )
    checked_in_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Worker tapped "作業完了" (complete-request); contractor then approves → completed.
    completion_requested_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Phase 2 fields: present in schema from day one, logic deferred. ---
    withholding_tax: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )  # (P2) employee route only
    checkin_lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)  # (P2)
    checkin_lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)  # (P2)
