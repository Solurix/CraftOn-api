"""User / session schemas for the auth endpoints."""

from __future__ import annotations

import datetime
import re
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.identifiers import looks_like_email, normalize_email, normalize_username
from app.models.enums import UserStatus, UserType
from app.schemas.contractor import ContractorProfileOut
from app.schemas.worker import WorkerProfileOut

# Usernames: letters/digits plus . _ - ; 3–64 chars. Compared lower-cased.
_USERNAME_RE = re.compile(r"^[a-z0-9._-]+$")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone_number: str
    username: str
    email: str
    user_type: UserType
    status: UserStatus
    display_name: str
    preferred_language: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class SessionCreateIn(BaseModel):
    """Body for ``POST /auth/session``.

    On first login the user row is created: a role and login credentials
    (username, email, password) are required. On subsequent logins the body is
    optional (an existing user is simply returned).
    """

    user_type: UserType | None = None
    display_name: str | None = None
    preferred_language: str | None = None
    username: str | None = Field(default=None, min_length=3, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def _norm_username(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = normalize_username(v)
        if not _USERNAME_RE.match(v):
            raise ValueError("username may contain only letters, digits, . _ -")
        return v

    @field_validator("email")
    @classmethod
    def _norm_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = normalize_email(v)
        if not looks_like_email(v):
            raise ValueError("invalid email address")
        return v


class SessionOut(BaseModel):
    user: UserOut
    created: bool
    # App session token — present after registration so the client is logged in
    # immediately without a second password round-trip.
    token: str | None = None


class SetPasswordIn(BaseModel):
    """Set/replace the current user's password (for OTP-free returning logins)."""

    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    """Returning login: username, email, or phone number + password."""

    identifier: str = Field(min_length=1, max_length=255)
    password: str


class LoginOut(BaseModel):
    """An app session token + the signed-in user."""

    token: str
    user: UserOut


class PasswordResetIn(BaseModel):
    """Reset the password for the phone number proven by the OTP token in the
    request (forgot-password flow). SMS OTP confirms phone ownership; no old
    password is needed."""

    password: str = Field(min_length=8, max_length=128)


class AccountUpdateIn(BaseModel):
    """Change login identifiers (username and/or email) from account settings.

    Both fields are optional; only the provided ones change. Normalized and
    uniqueness-checked exactly like registration."""

    username: str | None = Field(default=None, min_length=3, max_length=64)
    email: str | None = Field(default=None, max_length=255)

    @field_validator("username")
    @classmethod
    def _norm_username(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = normalize_username(v)
        if not _USERNAME_RE.match(v):
            raise ValueError("username may contain only letters, digits, . _ -")
        return v

    @field_validator("email")
    @classmethod
    def _norm_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = normalize_email(v)
        if not looks_like_email(v):
            raise ValueError("invalid email address")
        return v


class MeOut(BaseModel):
    user: UserOut
    has_worker_profile: bool = False
    has_contractor_profile: bool = False
    has_password: bool = False
    worker_profile: WorkerProfileOut | None = None
    contractor_profile: ContractorProfileOut | None = None
