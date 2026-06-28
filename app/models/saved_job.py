"""saved_jobs — a worker bookmarking a job to revisit/apply later.

One row per (worker, job). Append-only bookmark; removing a bookmark deletes the
row. Cascades on both the worker and the job so stale bookmarks clean themselves.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPKMixin


class SavedJob(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "saved_jobs"
    __table_args__ = (
        UniqueConstraint("worker_id", "job_id", name="uq_saved_jobs_worker_id_job_id"),
        Index("ix_saved_jobs_worker_id_created_at", "worker_id", "created_at"),
    )

    worker_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
