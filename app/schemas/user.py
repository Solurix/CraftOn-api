"""User / session schemas for the auth endpoints."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import UserStatus, UserType


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone_number: str
    user_type: UserType
    status: UserStatus
    display_name: str
    preferred_language: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class SessionCreateIn(BaseModel):
    """Body for ``POST /auth/session``.

    On first login the user row is created and a role is required. On subsequent
    logins the body is optional (an existing user is simply returned).
    """

    user_type: UserType | None = None
    display_name: str | None = None
    preferred_language: str | None = None


class SessionOut(BaseModel):
    user: UserOut
    created: bool


class MeOut(BaseModel):
    user: UserOut
    # Onboarding/profile payloads are attached in build-order step 2.
    has_worker_profile: bool = False
    has_contractor_profile: bool = False
