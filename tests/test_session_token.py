"""App session token: issue/verify round-trip, tamper + expiry + foreign tokens."""

from __future__ import annotations

import uuid

import pytest

from app.core.auth import make_fake_token
from app.core.session_token import (
    InvalidSessionTokenError,
    issue_session_token,
    verify_session_token,
)
from app.models.enums import UserType
from app.models.user import User


def _user() -> User:
    return User(
        id=uuid.uuid4(),
        phone_number="+819000000000",
        username="alice",
        email="alice@example.com",
        user_type=UserType.WORKER,
        display_name="Alice",
    )


def test_issue_and_verify_roundtrip() -> None:
    user = _user()
    claims = verify_session_token(issue_session_token(user))
    assert claims.sub == str(user.id)
    assert claims.phone_number == user.phone_number
    assert claims.user_type == "worker"


def test_tampered_signature_rejected() -> None:
    token = issue_session_token(_user())
    header, payload, _sig = token.split(".")
    forged = f"{header}.{payload}.AAAAdeadbeef"
    with pytest.raises(InvalidSessionTokenError):
        verify_session_token(forged)


def test_expired_token_rejected() -> None:
    user = _user()
    token = issue_session_token(user, now=1_000)
    # Far in the future, well past the TTL.
    with pytest.raises(InvalidSessionTokenError):
        verify_session_token(token, now=10_000_000_000)


def test_foreign_otp_token_is_not_a_session_token() -> None:
    # A fake OTP token (base64url JSON, no signature) is not one of our tokens.
    with pytest.raises(InvalidSessionTokenError):
        verify_session_token(make_fake_token("+819000000000"))
