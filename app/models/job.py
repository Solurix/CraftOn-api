"""jobs — a posting by a contractor (trades needed on a date/site)."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, Time, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import JobStatus, pg_enum


class Job(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    # Supports the job-search query (docs/05 indexing notes).
    __table_args__ = (
        Index("ix_jobs_status_work_date_prefecture", "status", "work_date", "prefecture"),
    )

    contractor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trades: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    work_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    # Asia/Tokyo business time-of-day.
    start_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    prefecture: Mapped[str] = mapped_column(String(64), nullable=False)
    area: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    daily_wage: Mapped[int] = mapped_column(Integer, nullable=False)  # JPY
    headcount: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Site/work photos attached to the posting — references to the contractor's
    # own `job_photo` documents, so one upload can be reused across postings
    # (no duplicate objects in Cloud Storage).
    photo_doc_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default=text("'{}'::uuid[]")
    )
    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus, "job_status"),
        nullable=False,
        server_default=text(f"'{JobStatus.OPEN.value}'"),
    )
