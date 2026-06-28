"""Admin (vetting) schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.contractor import ContractorProfileOut
from app.schemas.document import DocumentWithUrlOut
from app.schemas.user import UserOut
from app.schemas.worker import WorkerProfileOut


class AdminCreateIn(BaseModel):
    """Create a new admin account by phone number."""

    phone_number: str = Field(min_length=5, max_length=32)
    display_name: str = Field(min_length=1, max_length=120)
    preferred_language: str = Field(default="ja", min_length=2, max_length=8)


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
