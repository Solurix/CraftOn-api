"""Worker onboarding / profile schemas."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UserStatus, WorkerClass


class WorkHistoryEntry(BaseModel):
    """A single past job in a worker's 職歴 (career history).

    Used for both input and output. Kept permissive (no min_length) so a stored
    row never fails OUT-serialization; the web/service drop blank-company rows on
    write.
    """

    company: str = Field(default="", max_length=255)
    trade: str = Field(default="", max_length=120)
    years: int = Field(default=0, ge=0, le=80)
    # Free-text summary of what the worker did there (概要). Candidate for
    # AI-assisted drafting later (docs/03 roadmap).
    description: str = Field(default="", max_length=2000)


class WorkerOnboardingIn(BaseModel):
    """Create/complete the worker profile (docs/04 §3.1)."""

    nationality: str = Field(min_length=2, max_length=2, description="ISO-ish: JP, VN, ID…")
    worker_class: WorkerClass
    display_name: str | None = None
    trades: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    has_insurance: bool = False
    bio: str | None = None
    years_experience: int = Field(default=0, ge=0)
    # Extended profile fields. Structured name parts are preferred; full_name
    # is composed from them server-side (kept for back-compat input/display).
    full_name: str | None = None
    family_name: str | None = Field(default=None, max_length=120)
    given_name: str | None = Field(default=None, max_length=120)
    middle_name: str | None = Field(default=None, max_length=120)
    name_kana: str | None = None
    email: str | None = None
    current_employer: str | None = None
    current_employer_public: bool = False
    prefecture: str | None = None
    area: str | None = None
    work_history: list[WorkHistoryEntry] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    # Non-JP only; the visa gate (docs/08) checks these at approval/confirm.
    residence_card_front_doc_id: uuid.UUID | None = None
    residence_card_back_doc_id: uuid.UUID | None = None
    visa_expiry_date: datetime.date | None = None
    work_restriction: str | None = None


class WorkerProfileUpdate(BaseModel):
    """PATCH /workers/me — all fields optional."""

    display_name: str | None = None
    nationality: str | None = Field(default=None, min_length=2, max_length=2)
    worker_class: WorkerClass | None = None
    trades: list[str] | None = None
    tools: list[str] | None = None
    has_insurance: bool | None = None
    bio: str | None = None
    years_experience: int | None = Field(default=None, ge=0)
    full_name: str | None = None
    family_name: str | None = Field(default=None, max_length=120)
    given_name: str | None = Field(default=None, max_length=120)
    middle_name: str | None = Field(default=None, max_length=120)
    name_kana: str | None = None
    email: str | None = None
    current_employer: str | None = None
    current_employer_public: bool | None = None
    prefecture: str | None = None
    area: str | None = None
    work_history: list[WorkHistoryEntry] | None = None
    qualifications: list[str] | None = None
    skills: list[str] | None = None
    residence_card_front_doc_id: uuid.UUID | None = None
    residence_card_back_doc_id: uuid.UUID | None = None
    visa_expiry_date: datetime.date | None = None
    work_restriction: str | None = None


class WorkerProfileOut(BaseModel):
    """Self/admin view (includes compliance-sensitive + PII fields)."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    display_name: str
    status: UserStatus
    nationality: str
    worker_class: WorkerClass
    trades: list[str]
    tools: list[str]
    has_insurance: bool
    bio: str | None
    years_experience: int
    full_name: str | None
    family_name: str | None
    given_name: str | None
    middle_name: str | None
    name_kana: str | None
    email: str | None
    current_employer: str | None
    current_employer_public: bool
    prefecture: str | None
    area: str | None
    work_history: list[WorkHistoryEntry]
    qualifications: list[str]
    skills: list[str]
    trust_score: Decimal
    visa_expiry_date: datetime.date | None
    work_restriction: str | None
    residence_card_front_doc_id: uuid.UUID | None
    residence_card_back_doc_id: uuid.UUID | None


class WorkerPublicOut(BaseModel):
    """Public worker profile (docs/06). Excludes PII (legal name, kana, email);
    current employer appears only when the worker opted to make it public."""

    user_id: uuid.UUID
    display_name: str
    worker_class: WorkerClass
    trades: list[str]
    tools: list[str]
    bio: str | None
    years_experience: int
    prefecture: str | None
    area: str | None
    current_employer: str | None
    work_history: list[WorkHistoryEntry]
    qualifications: list[str]
    skills: list[str]
    trust_score: Decimal
