"""Matching schemas."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import ContractType, FeeStatus, MatchingStatus


class MatchingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    worker_id: uuid.UUID
    application_id: uuid.UUID
    status: MatchingStatus
    contract_type: ContractType
    daily_wage: int
    platform_fee: int
    fee_status: FeeStatus
    checked_in_at: datetime.datetime | None
    completion_requested_at: datetime.datetime | None
    completed_at: datetime.datetime | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    # Convenience fields populated by the router (not columns).
    contractor_id: uuid.UUID | None = None
    worker_display_name: str | None = None
    contractor_company_name: str | None = None
    work_date: datetime.date | None = None
    prefecture: str | None = None
    # Generated, localized placeholder contract terms (docs/08), computed on read.
    terms: str | None = None


class WorkHistoryOut(BaseModel):
    """A worker's completed-work record + headline totals (informational)."""

    completed_count: int
    total_earned: int  # JPY, sum of agreed daily wages for completed jobs
    matchings: list[MatchingOut]
