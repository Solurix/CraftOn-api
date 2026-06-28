"""Contractor onboarding / profile schemas."""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import UserStatus


class ContractorOnboardingIn(BaseModel):
    company_name: str
    contact_person: str
    prefecture: str
    address: str | None = None
    bio: str | None = None
    display_name: str | None = None


class ContractorProfileUpdate(BaseModel):
    company_name: str | None = None
    contact_person: str | None = None
    prefecture: str | None = None
    address: str | None = None
    bio: str | None = None
    display_name: str | None = None


class ContractorProfileOut(BaseModel):
    """Self/admin view."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    display_name: str
    status: UserStatus
    company_name: str
    contact_person: str
    prefecture: str
    address: str | None
    bio: str | None
    rating: Decimal


class ContractorPublicOut(BaseModel):
    """Public contractor profile (docs/06: rating, reviews)."""

    user_id: uuid.UUID
    display_name: str
    company_name: str
    prefecture: str
    bio: str | None
    rating: Decimal
