"""Admin (vetting) schemas."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.contractor import ContractorProfileOut
from app.schemas.document import DocumentWithUrlOut
from app.schemas.user import UserOut
from app.schemas.worker import WorkerProfileOut


class RejectIn(BaseModel):
    reason: str | None = None


class SuspendIn(BaseModel):
    suspend: bool = True


class VettingItem(BaseModel):
    user: UserOut
    worker_profile: WorkerProfileOut | None = None
    contractor_profile: ContractorProfileOut | None = None
    documents: list[DocumentWithUrlOut] = []


class VettingQueueOut(BaseModel):
    items: list[VettingItem]
