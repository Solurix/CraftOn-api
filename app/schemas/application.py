"""Application schemas."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import ApplicationStatus, WorkerClass


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    worker_id: uuid.UUID
    status: ApplicationStatus
    created_at: datetime.datetime


class ApplicantOut(ApplicationOut):
    """Applicant view for the contractor (worker summary embedded)."""

    worker_display_name: str
    worker_class: WorkerClass
    worker_trust_score: Decimal
