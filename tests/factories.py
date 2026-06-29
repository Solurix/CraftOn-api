"""Small builders for test request payloads."""

from __future__ import annotations

import uuid
from typing import Any


def signup_payload(**overrides: Any) -> dict[str, Any]:
    """A ``POST /auth/session`` registration body with unique credentials.

    Registration now requires username/email/password; this fills them with
    collision-free values so callers only specify what the test cares about
    (role, display_name, …).
    """
    handle = "u" + uuid.uuid4().hex[:12]
    body: dict[str, Any] = {
        "username": handle,
        "email": f"{handle}@test.local",
        "password": "test-password-123",
    }
    body.update(overrides)
    return body
