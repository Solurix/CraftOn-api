"""Login-identifier normalization.

Users may log in with their username, email, or phone number. Username and email
are stored and compared **lower-cased** so lookup/uniqueness is case-insensitive;
phone numbers are kept verbatim (already E.164, e.g. ``+8190...``).
"""

from __future__ import annotations


def normalize_username(value: str) -> str:
    return value.strip().lower()


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str) -> str:
    return value.strip()


def looks_like_email(value: str) -> bool:
    """Cheap heuristic — an ``@`` is enough to route a login identifier to email."""
    return "@" in value


def looks_like_phone(value: str) -> bool:
    """Phone identifiers are numeric, optionally ``+``-prefixed (E.164)."""
    stripped = value.strip().lstrip("+")
    return stripped.isdigit() and len(stripped) >= 5
