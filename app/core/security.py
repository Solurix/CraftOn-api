"""Password hashing (PBKDF2-HMAC-SHA256, stdlib only — no extra dependency).

Format: ``pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return (
        f"{_ALGO}${_ITERATIONS}$"
        f"{base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"
    )


# A throwaway hash to verify against on negative login paths (unknown user / no
# password set) so every attempt spends the same KDF cost — closes the timing
# side-channel that would otherwise enumerate accounts. See auth.login.
DUMMY_HASH = hash_password(base64.b64encode(os.urandom(16)).decode())


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, iters, salt_b64, dk_b64 = stored.split("$")
        if algo != _ALGO:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False
