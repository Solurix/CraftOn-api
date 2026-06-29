"""Admin (vetting) schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.contractor import ContractorProfileOut
from app.schemas.document import DocumentWithUrlOut
from app.schemas.user import UserOut
from app.schemas.worker import WorkerProfileOut


class AdminCreateIn(BaseModel):
    """Create a new admin account (logs in with identifier + password)."""

    phone_number: str = Field(min_length=5, max_length=32)
    username: str = Field(min_length=3, max_length=64)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    preferred_language: str = Field(default="ja", min_length=2, max_length=8)


class DebugSeedIn(BaseModel):
    """How many random records to create (debug/non-prod only)."""

    workers: int = Field(default=5, ge=0, le=100)
    contractors: int = Field(default=3, ge=0, le=50)
    jobs: int = Field(default=10, ge=0, le=200)


class DebugSeedOut(BaseModel):
    workers: int
    contractors: int
    jobs: int


class RejectIn(BaseModel):
    reason: str | None = None


class SuspendIn(BaseModel):
    suspend: bool = True


class ConfigOut(BaseModel):
    """Resolved config/flags snapshot (runtime override > env > default)."""

    config: dict[str, Any]


class ConfigUpdateIn(BaseModel):
    updates: dict[str, Any] = Field(min_length=1)


class VettingItem(BaseModel):
    user: UserOut
    worker_profile: WorkerProfileOut | None = None
    contractor_profile: ContractorProfileOut | None = None
    documents: list[DocumentWithUrlOut] = []


class VettingQueueOut(BaseModel):
    items: list[VettingItem]
