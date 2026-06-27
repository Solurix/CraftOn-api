"""applications — a worker applying to a job (one per job/worker)."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPKMixin
from app.models.enums import ApplicationStatus, pg_enum


class Application(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("job_id", "worker_id", name="uq_applications_job_id_worker_id"),
        Index("ix_applications_worker_id_status", "worker_id", "status"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    worker_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        pg_enum(ApplicationStatus, "application_status"),
        nullable=False,
        server_default=text(f"'{ApplicationStatus.APPLIED.value}'"),
    )
