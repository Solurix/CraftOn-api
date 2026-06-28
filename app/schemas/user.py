"""User / session schemas for the auth endpoints."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UserStatus, UserType
from app.schemas.contractor import ContractorProfileOut
from app.schemas.worker import WorkerProfileOut


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


class SetPasswordIn(BaseModel):
    """Set/replace the current user's password (for OTP-free returning logins)."""

    password: str = Field(min_length=8, max_length=128)


class PasswordLoginIn(BaseModel):
    phone_number: str
    password: str


class PasswordLoginOut(BaseModel):
    """A bearer token (accepted by the API verifier) + the signed-in user."""

    token: str
    user: UserOut


class MeOut(BaseModel):
    user: UserOut
    has_worker_profile: bool = False
    has_contractor_profile: bool = False
    has_password: bool = False
    worker_profile: WorkerProfileOut | None = None
    contractor_profile: ContractorProfileOut | None = None
