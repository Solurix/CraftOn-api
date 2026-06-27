"""Firebase ID-token verification.

The API is stateless: every request carries ``Authorization: Bearer <token>``
and we verify it per request. Verification is abstracted behind
:class:`TokenVerifier` so:

* **prod/staging** use :class:`FirebaseTokenVerifier` (real Firebase Auth), and
* **local/dev/CI/tests** use :class:`FakeTokenVerifier` — no GCP needed.

Select via ``CRAFTON_AUTH_MODE`` (``firebase`` | ``fake``). The verifier returns
:class:`FirebaseClaims`; mapping claims → ``users`` row happens in the API layer.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

from app.core.config import AuthMode, get_settings


@dataclass(frozen=True)
class FirebaseClaims:
    """The subset of verified token claims the app needs."""

    uid: str
    phone_number: str | None
    raw: dict[str, Any]


class InvalidTokenError(Exception):
    """Raised when a token cannot be verified. The API maps this to 401."""


class TokenVerifier(Protocol):
    def verify(self, token: str) -> FirebaseClaims: ...


# ---------------------------------------------------------------------------
# Fake verifier (local/dev/CI/tests) — no GCP, no network.
# ---------------------------------------------------------------------------

def make_fake_token(phone_number: str, uid: str | None = None, **extra: Any) -> str:
    """Build a fake bearer token: base64url(JSON). For dev/tests only."""
    payload: dict[str, Any] = {"uid": uid or f"fake-{phone_number}", "phone_number": phone_number}
    payload.update(extra)
    raw = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class FakeTokenVerifier:
    """Decodes :func:`make_fake_token` payloads. Accepts base64url(JSON) or raw JSON."""

    def verify(self, token: str) -> FirebaseClaims:
        payload = self._decode(token)
        uid = payload.get("uid")
        if not uid:
            raise InvalidTokenError("fake token missing 'uid'")
        return FirebaseClaims(
            uid=str(uid),
            phone_number=payload.get("phone_number"),
            raw=payload,
        )

    @staticmethod
    def _decode(token: str) -> dict[str, Any]:
        token = token.strip()
        # Try base64url (pad to a multiple of 4) first, then raw JSON.
        try:
            padded = token + "=" * (-len(token) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
            data = json.loads(decoded)
        except (binascii.Error, ValueError, UnicodeDecodeError):
            try:
                data = json.loads(token)
            except json.JSONDecodeError as exc:
                raise InvalidTokenError("malformed fake token") from exc
        if not isinstance(data, dict):
            raise InvalidTokenError("fake token payload must be an object")
        return data


# ---------------------------------------------------------------------------
# Real Firebase verifier (dev/staging/prod).
# ---------------------------------------------------------------------------

class FirebaseTokenVerifier:
    """Verifies real Firebase ID tokens via ``firebase-admin`` (lazy-imported)."""

    def __init__(self, project_id: str) -> None:
        self._project_id = project_id
        self._initialized = False

    def _ensure_app(self) -> None:
        if self._initialized:
            return
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            # Application Default Credentials (Cloud Run SA) or
            # GOOGLE_APPLICATION_CREDENTIALS for the service account.
            firebase_admin.initialize_app(
                credentials.ApplicationDefault(), {"projectId": self._project_id}
            )
        self._initialized = True

    def verify(self, token: str) -> FirebaseClaims:
        self._ensure_app()
        from firebase_admin import auth as fb_auth

        try:
            decoded: dict[str, Any] = fb_auth.verify_id_token(token)
        except Exception as exc:  # firebase-admin raises several subtypes
            raise InvalidTokenError(str(exc)) from exc
        return FirebaseClaims(
            uid=decoded["uid"],
            phone_number=decoded.get("phone_number"),
            raw=decoded,
        )


@lru_cache
def get_verifier() -> TokenVerifier:
    settings = get_settings()
    if settings.auth_mode is AuthMode.FIREBASE:
        return FirebaseTokenVerifier(settings.firebase_project_id)
    return FakeTokenVerifier()
