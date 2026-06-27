"""Worker onboarding / profile schemas."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UserStatus, WorkerClass


class WorkerOnboardingIn(BaseModel):
    """Create/complete the worker profile (docs/04 §3.1)."""

    nationality: str = Field(min_length=2, max_length=2, description="ISO-ish: JP, VN, ID…")
    worker_class: WorkerClass
    display_name: str | None = None
    trades: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    has_insurance: bool = False
    # Non-JP only; the visa gate (docs/08) checks these at approval/confirm.
    residence_card_front_doc_id: uuid.UUID | None = None
    residence_card_back_doc_id: uuid.UUID | None = None
    visa_expiry_date: datetime.date | None = None
    work_restriction: str | None = None


class WorkerProfileUpdate(BaseModel):
    """PATCH /workers/me — all fields optional."""

    display_name: str | None = None
    trades: list[str] | None = None
    tools: list[str] | None = None
    has_insurance: bool | None = None
    residence_card_front_doc_id: uuid.UUID | None = None
    residence_card_back_doc_id: uuid.UUID | None = None
    visa_expiry_date: datetime.date | None = None
    work_restriction: str | None = None


class WorkerProfileOut(BaseModel):
    """Self/admin view (includes compliance-sensitive fields)."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    display_name: str
    status: UserStatus
    nationality: str
    worker_class: WorkerClass
    trades: list[str]
    tools: list[str]
    has_insurance: bool
    trust_score: Decimal
    visa_expiry_date: datetime.date | None
    work_restriction: str | None
    residence_card_front_doc_id: uuid.UUID | None
    residence_card_back_doc_id: uuid.UUID | None


class WorkerPublicOut(BaseModel):
    """Public worker profile (docs/06: reviews, trust, trades)."""

    user_id: uuid.UUID
    display_name: str
    worker_class: WorkerClass
    trades: list[str]
    tools: list[str]
    trust_score: Decimal
