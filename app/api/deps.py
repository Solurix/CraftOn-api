"""Shared FastAPI dependencies: DB session, config, auth, and role guards."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import errors
from app.core.auth import FirebaseClaims, InvalidTokenError, get_verifier
from app.core.config import ConfigService
from app.core.session_token import InvalidSessionTokenError, verify_session_token
from app.db.session import get_db
from app.models.enums import UserType
from app.models.user import User

if TYPE_CHECKING:
    from app.core.storage import StorageService

# auto_error=False so we can return our own localized error envelope.
_bearer = HTTPBearer(
    auto_error=False, description="App session token (or, at registration, a Firebase ID token)"
)


def get_config(db: Session = Depends(get_db)) -> ConfigService:
    return ConfigService(db)


def get_storage_service() -> StorageService:
    from app.core.storage import get_storage

    return get_storage()


def get_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> FirebaseClaims:
    """Verify the bearer token and return its claims (401 if missing/invalid).

    Accepts either an **app session token** (issued by login/registration — the
    normal case) or, as a fallback, an **OTP token** (Firebase/fake) used once at
    registration. Both expose ``phone_number``, which downstream resolves to the
    user row.
    """
    if credentials is None or not credentials.credentials:
        raise errors.unauthorized()
    token = credentials.credentials
    try:
        session = verify_session_token(token)
        return FirebaseClaims(
            uid=session.sub, phone_number=session.phone_number, raw=session.raw
        )
    except InvalidSessionTokenError:
        pass  # Not one of our tokens — try the OTP verifier (registration path).
    try:
        return get_verifier().verify(token)
    except InvalidTokenError as exc:
        raise errors.unauthorized("error.auth.invalid_token") from exc


def get_current_user(
    request: Request,
    claims: FirebaseClaims = Depends(get_claims),
    db: Session = Depends(get_db),
) -> User:
    """Map verified claims to the ``users`` row (401 if not yet onboarded).

    First-time users must call ``POST /auth/session`` to create their row.
    """
    if not claims.phone_number:
        raise errors.unauthorized("error.auth.no_phone")
    user = db.scalar(select(User).where(User.phone_number == claims.phone_number))
    if user is None:
        raise errors.unauthorized()
    # Localize subsequent errors to the user's preference.
    request.state.locale = user.preferred_language
    # Record/refresh the calling device (and reject it if revoked). Header-gated,
    # so non-device clients (server-to-server, tests) are unaffected.
    device_id = request.headers.get("x-device-id")
    if device_id:
        import datetime

        from app.services import devices

        devices.touch_device(
            db,
            user,
            device_id,
            request.headers.get("x-device-name"),
            datetime.datetime.now(datetime.UTC),
        )
    return user


def require_active(user: User = Depends(get_current_user)) -> User:
    """Block suspended accounts from acting (read-only /me stays accessible)."""
    from app.models.enums import UserStatus

    if user.status is UserStatus.SUSPENDED:
        raise errors.forbidden("error.user.suspended")
    return user


def require_roles(*roles: UserType) -> Callable[..., User]:
    """Build a dependency that allows only the given roles (403 otherwise)."""

    def _guard(user: User = Depends(require_active)) -> User:
        if user.user_type not in roles:
            raise errors.forbidden()
        return user

    return _guard


def require_approved(user: User = Depends(require_active)) -> User:
    """Require an approved account (for actions gated behind vetting)."""
    from app.models.enums import UserStatus

    if user.status is not UserStatus.APPROVED:
        raise errors.forbidden("error.user.not_approved")
    return user


# Convenience role dependencies (active = not suspended; pending allowed).
def worker_user(user: User = Depends(require_roles(UserType.WORKER))) -> User:
    return user


def contractor_user(user: User = Depends(require_roles(UserType.CONTRACTOR))) -> User:
    return user


def admin_user(user: User = Depends(require_roles(UserType.ADMIN))) -> User:
    return user


# Approved + specific role (for actions gated behind vetting, e.g. posting/applying).
def approved_worker(user: User = Depends(require_approved)) -> User:
    if user.user_type is not UserType.WORKER:
        raise errors.forbidden()
    return user


def approved_contractor(user: User = Depends(require_approved)) -> User:
    if user.user_type is not UserType.CONTRACTOR:
        raise errors.forbidden()
    return user
