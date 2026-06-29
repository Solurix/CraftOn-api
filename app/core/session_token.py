"""App-issued session tokens (signed JWT, HS256, stdlib only).

After registration (phone OTP) or a returning identifier+password login, the API
mints its **own** short-lived bearer token rather than relying on a Firebase ID
token. This is what authenticates every subsequent request; the Firebase/fake OTP
token is only used once, at ``POST /auth/session``.

Format is a standard compact JWT ``header.payload.signature`` with an HMAC-SHA256
signature over ``base64url(header).base64url(payload)`` — implemented with the
stdlib (``hmac``/``hashlib``/``base64``), matching the no-extra-dependency style of
:mod:`app.core.security`.

Claims: ``sub`` (user id), ``phone_number`` (the canonical lookup key the auth
dependency resolves), ``user_type``, ``iss="crafton"``, ``iat``, ``exp``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.config import get_settings

if TYPE_CHECKING:
    from app.models.user import User

_ALG = "HS256"
_ISS = "crafton"
_HEADER = {"alg": _ALG, "typ": "JWT"}


@dataclass(frozen=True)
class SessionClaims:
    """Verified claims carried by an app session token."""

    sub: str
    phone_number: str
    user_type: str
    raw: dict[str, Any]


class InvalidSessionTokenError(Exception):
    """Raised when a session token fails verification (bad signature/expiry/shape)."""


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _sign(signing_input: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return _b64url_encode(sig)


def issue_session_token(user: User, *, now: int | None = None) -> str:
    """Mint a signed session token for ``user`` (valid for ``session_ttl_seconds``)."""
    settings = get_settings()
    issued = int(now if now is not None else time.time())
    payload = {
        "sub": str(user.id),
        "phone_number": user.phone_number,
        "user_type": user.user_type.value,
        "iss": _ISS,
        "iat": issued,
        "exp": issued + settings.session_ttl_seconds,
    }
    header_seg = _b64url_encode(json.dumps(_HEADER, separators=(",", ":")).encode())
    payload_seg = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_seg}.{payload_seg}".encode("ascii")
    return f"{header_seg}.{payload_seg}.{_sign(signing_input, settings.session_secret)}"


def verify_session_token(token: str, *, now: int | None = None) -> SessionClaims:
    """Verify signature + expiry and return the claims, or raise InvalidSessionTokenError."""
    settings = get_settings()
    try:
        header_seg, payload_seg, sig = token.strip().split(".")
    except ValueError as exc:
        raise InvalidSessionTokenError("malformed token") from exc

    signing_input = f"{header_seg}.{payload_seg}".encode("ascii")
    expected = _sign(signing_input, settings.session_secret)
    if not hmac.compare_digest(expected, sig):
        raise InvalidSessionTokenError("bad signature")

    try:
        payload = json.loads(_b64url_decode(payload_seg))
    except (ValueError, json.JSONDecodeError) as exc:
        raise InvalidSessionTokenError("malformed payload") from exc

    if not isinstance(payload, dict) or payload.get("iss") != _ISS:
        raise InvalidSessionTokenError("unexpected issuer")

    current = int(now if now is not None else time.time())
    exp = payload.get("exp")
    if not isinstance(exp, int) or current >= exp:
        raise InvalidSessionTokenError("expired")

    sub = payload.get("sub")
    phone = payload.get("phone_number")
    if not sub or not phone:
        raise InvalidSessionTokenError("missing subject")
    # Reject a syntactically invalid subject early (defends downstream lookups).
    try:
        uuid.UUID(str(sub))
    except ValueError as exc:
        raise InvalidSessionTokenError("invalid subject") from exc

    return SessionClaims(
        sub=str(sub),
        phone_number=str(phone),
        user_type=str(payload.get("user_type", "")),
        raw=payload,
    )
