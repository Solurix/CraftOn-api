"""Job schemas."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import JobStatus


class JobCreate(BaseModel):
    trades: list[str] = Field(min_length=1)
    work_date: datetime.date
    start_time: datetime.time
    end_time: datetime.time
    prefecture: str
    area: str | None = None
    address: str | None = None
    daily_wage: int = Field(gt=0, description="JPY, integer")
    headcount: int = Field(default=1, ge=1)
    notes: str | None = None
    # References to the contractor's own job_photo documents (reusable across
    # postings — no duplicate uploads).
    photo_doc_ids: list[uuid.UUID] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def _check_times(self) -> JobCreate:
        # Night shifts are allowed: an end_time at or before start_time means
        # the shift ends on the NEXT day (e.g. 21:00–05:00, entered as
        # 21:00–29:00 in the UI). Only an exactly-equal pair is rejected as
        # ambiguous (0h vs 24h).
        if self.end_time == self.start_time:
            raise ValueError("end_time must differ from start_time")
        return self


class JobUpdate(BaseModel):
    trades: list[str] | None = Field(default=None, min_length=1)
    work_date: datetime.date | None = None
    start_time: datetime.time | None = None
    end_time: datetime.time | None = None
    prefecture: str | None = None
    area: str | None = None
    address: str | None = None
    daily_wage: int | None = Field(default=None, gt=0)
    headcount: int | None = Field(default=None, ge=1)
    notes: str | None = None
    photo_doc_ids: list[uuid.UUID] | None = Field(default=None, max_length=12)


class JobPhotoOut(BaseModel):
    """A posting photo: document reference + short-lived signed read URL."""

    document_id: uuid.UUID
    read_url: str


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contractor_id: uuid.UUID
    contractor_company_name: str | None = None
    trades: list[str]
    work_date: datetime.date
    start_time: datetime.time
    end_time: datetime.time
    prefecture: str
    area: str | None
    address: str | None
    daily_wage: int
    headcount: int
    notes: str | None
    photo_doc_ids: list[uuid.UUID]
    status: JobStatus
    created_at: datetime.datetime
    updated_at: datetime.datetime
