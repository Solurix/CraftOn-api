"""Auth & session endpoints: exchange a Firebase token for the app user.

SMS OTP itself is handled by Firebase on the client; the API only verifies the
resulting ID token (via the configured verifier) and maps it to a ``users`` row.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_claims, get_current_user
from app.core import errors, security
from app.core.auth import FirebaseClaims, make_fake_token
from app.core.config import AuthMode, get_settings
from app.core.i18n import resolve_locale
from app.db.session import get_db
from app.models.enums import UserType
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.user import (
    MeOut,
    PasswordLoginIn,
    PasswordLoginOut,
    SessionCreateIn,
    SessionOut,
    SetPasswordIn,
    UserOut,
)

router = APIRouter(tags=["auth"])

# Roles a user may self-assign at signup. Admins are provisioned out-of-band.
_SIGNUP_ROLES = {UserType.WORKER, UserType.CONTRACTOR}


def _default_display_name(phone_number: str) -> str:
    # Provisional handle; the onboarding step replaces it with a real nickname.
    suffix = phone_number[-4:] if len(phone_number) >= 4 else phone_number
    return f"user-{suffix}"


@router.post(
    "/auth/session",
    response_model=SessionOut,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
def create_session(
    request: Request,
    response: Response,
    payload: SessionCreateIn,
    claims: FirebaseClaims = Depends(get_claims),
    db: Session = Depends(get_db),
) -> SessionOut:
    """Create the user on first login (role required) or return the existing one."""
    if not claims.phone_number:
        raise errors.unauthorized("error.auth.no_phone")

    user = db.scalar(select(User).where(User.phone_number == claims.phone_number))
    if user is not None:
        request.state.locale = user.preferred_language
        if payload.preferred_language and payload.preferred_language in ("ja", "en"):
            user.preferred_language = payload.preferred_language
            db.commit()
        return SessionOut(user=UserOut.model_validate(user), created=False)

    # First login → create. A role is required and must be self-assignable.
    if payload.user_type is None:
        raise errors.bad_request("role_required", "error.user.role_required")
    if payload.user_type not in _SIGNUP_ROLES:
        raise errors.bad_request("invalid_role", "error.user.invalid_role")

    locale = resolve_locale(
        request.headers.get("accept-language"), payload.preferred_language
    )
    user = User(
        phone_number=claims.phone_number,
        user_type=payload.user_type,
        display_name=payload.display_name or _default_display_name(claims.phone_number),
        preferred_language=locale,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    request.state.locale = user.preferred_language
    response.status_code = status.HTTP_201_CREATED
    return SessionOut(user=UserOut.model_validate(user), created=True)


@router.post(
    "/auth/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"model": ErrorResponse}},
)
def set_password(
    payload: SetPasswordIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Set/replace the caller's password (used for OTP-free returning logins)."""
    user.password_hash = security.hash_password(payload.password)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/auth/password-login",
    response_model=PasswordLoginOut,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
def password_login(
    payload: PasswordLoginIn,
    request: Request,
    db: Session = Depends(get_db),
) -> PasswordLoginOut:
    """Phone + password → a bearer token, skipping OTP. Returns the same token
    format the API verifier accepts. (Real Firebase password exchange is a later
    GCP concern; only the fake/dev verifier can mint tokens here.)"""
    if get_settings().auth_mode is not AuthMode.FAKE:
        raise errors.bad_request(
            "password_login_unsupported", "error.auth.password_login_unsupported"
        )
    user = db.scalar(select(User).where(User.phone_number == payload.phone_number))
    if user is None or not security.verify_password(payload.password, user.password_hash):
        raise errors.unauthorized("error.auth.invalid_credentials")
    request.state.locale = user.preferred_language
    return PasswordLoginOut(
        token=make_fake_token(user.phone_number),
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=MeOut, responses={401: {"model": ErrorResponse}})
def get_me(user: User = Depends(get_current_user)) -> MeOut:
    """Current user + their profile (if onboarded)."""
    from app.api.v1.onboarding import contractor_out, worker_out

    worker = (
        worker_out(user.worker_profile, user) if user.worker_profile is not None else None
    )
    contractor = (
        contractor_out(user.contractor_profile, user)
        if user.contractor_profile is not None
        else None
    )
    return MeOut(
        user=UserOut.model_validate(user),
        has_worker_profile=worker is not None,
        has_contractor_profile=contractor is not None,
        has_password=user.password_hash is not None,
        worker_profile=worker,
        contractor_profile=contractor,
    )
