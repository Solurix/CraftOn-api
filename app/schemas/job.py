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

    @model_validator(mode="after")
    def _check_times(self) -> JobCreate:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
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
    status: JobStatus
    created_at: datetime.datetime
    updated_at: datetime.datetime
