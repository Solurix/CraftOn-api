"""Auth & session endpoints.

Registration is gated by SMS OTP: the client completes Firebase phone OTP and the
API verifies the resulting ID token (via the configured verifier) at
``POST /auth/session``, where it also captures the user's login credentials
(username, email, password). From then on the user signs in with
``POST /auth/login`` using any identifier (username / email / phone) + password —
**no OTP** — and the API issues its own signed session token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_claims, get_current_user, require_active
from app.core import errors, security
from app.core.auth import FirebaseClaims
from app.core.i18n import resolve_locale
from app.core.identifiers import normalize_email, normalize_phone, normalize_username
from app.core.session_token import issue_session_token
from app.db.session import get_db
from app.models.enums import UserType
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.user import (
    LoginIn,
    LoginOut,
    MeOut,
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
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def create_session(
    request: Request,
    response: Response,
    payload: SessionCreateIn,
    claims: FirebaseClaims = Depends(get_claims),
    db: Session = Depends(get_db),
) -> SessionOut:
    """Register on first login (OTP + role + credentials) or return the existing user."""
    if not claims.phone_number:
        raise errors.unauthorized("error.auth.no_phone")

    user = db.scalar(select(User).where(User.phone_number == claims.phone_number))
    if user is not None:
        request.state.locale = user.preferred_language
        if payload.preferred_language and payload.preferred_language in ("ja", "en"):
            user.preferred_language = payload.preferred_language
            db.commit()
        return SessionOut(user=UserOut.model_validate(user), created=False)

    # First login → register. Role + login credentials are required.
    if payload.user_type is None:
        raise errors.bad_request("role_required", "error.user.role_required")
    if payload.user_type not in _SIGNUP_ROLES:
        raise errors.bad_request("invalid_role", "error.user.invalid_role")
    if not payload.username or not payload.email or not payload.password:
        raise errors.bad_request("credentials_required", "error.user.credentials_required")

    # Enforce identifier uniqueness up front (the DB unique constraints are the
    # final guard, but this returns a clean, localized 409).
    clash = db.scalar(
        select(User).where(
            or_(User.username == payload.username, User.email == payload.email)
        )
    )
    if clash is not None:
        if clash.username == payload.username:
            raise errors.conflict("username_taken", "error.user.username_taken")
        raise errors.conflict("email_taken", "error.user.email_taken")

    locale = resolve_locale(
        request.headers.get("accept-language"), payload.preferred_language
    )
    user = User(
        phone_number=claims.phone_number,
        username=payload.username,
        email=payload.email,
        user_type=payload.user_type,
        display_name=payload.display_name or _default_display_name(claims.phone_number),
        preferred_language=locale,
        password_hash=security.hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    request.state.locale = user.preferred_language
    response.status_code = status.HTTP_201_CREATED
    return SessionOut(
        user=UserOut.model_validate(user),
        created=True,
        token=issue_session_token(user),
    )


@router.post(
    "/auth/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"model": ErrorResponse}},
)
def set_password(
    payload: SetPasswordIn,
    user: User = Depends(require_active),
    db: Session = Depends(get_db),
) -> Response:
    """Set/replace the caller's password.

    Gated behind ``require_active`` so a suspended account cannot establish or
    rotate credentials.
    """
    user.password_hash = security.hash_password(payload.password)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/auth/login",
    response_model=LoginOut,
    responses={401: {"model": ErrorResponse}},
)
def login(
    payload: LoginIn,
    request: Request,
    db: Session = Depends(get_db),
) -> LoginOut:
    """Returning login: username / email / phone + password → a session token.

    SMS OTP is only used at registration; this path is OTP-free and works in every
    environment (the API issues its own signed token — see core.session_token).

    SECURITY — before exposing this widely, add per-identifier + per-IP rate
    limiting / lockout on failed attempts (config-driven) and consider binding
    tokens to the device record so revocation invalidates them server-side.
    """
    ident = payload.identifier.strip()
    user = db.scalar(
        select(User).where(
            or_(
                User.username == normalize_username(ident),
                User.email == normalize_email(ident),
                User.phone_number == normalize_phone(ident),
            )
        )
    )
    # Always run one full KDF (against a dummy hash on the negative paths) so the
    # response time doesn't reveal whether the account exists / has a password.
    stored = user.password_hash if user is not None else None
    ok = security.verify_password(payload.password, stored or security.DUMMY_HASH)
    if user is None or stored is None or not ok:
        raise errors.unauthorized("error.auth.invalid_credentials")
    request.state.locale = user.preferred_language
    return LoginOut(token=issue_session_token(user), user=UserOut.model_validate(user))


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
