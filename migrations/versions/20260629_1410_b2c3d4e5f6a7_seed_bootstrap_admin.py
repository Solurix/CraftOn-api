"""seed bootstrap admin (admin / admin)

Seeds a single, already-approved admin account so a fresh deployment has someone
who can sign in and provision real admins. The account logs in like any user:
identifier (username/email/phone) + password.

⚠️  SECURITY: ``admin`` / ``admin`` is a deliberately weak bootstrap credential.
Rotate the password (or delete this account and create a real admin) immediately
after first use. Do NOT rely on it in production.

Idempotent: does nothing if a user named ``admin`` already exists.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-29 14:10:00.000000+00:00
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

from app.core.security import hash_password


revision: str = 'b2c3d4e5f6a7'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USERNAME = "admin"
_PASSWORD = "admin"  # bootstrap only — see module docstring.


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        text("SELECT 1 FROM users WHERE username = :u"), {"u": _USERNAME}
    ).first()
    if exists is not None:
        return
    conn.execute(
        text(
            """
            INSERT INTO users (
                id, phone_number, username, email, user_type, status,
                display_name, preferred_language, password_hash,
                created_at, updated_at
            ) VALUES (
                :id, :phone, :username, :email,
                CAST(:user_type AS user_type), CAST(:status AS user_status),
                :display_name, :lang, :pw, now(), now()
            )
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "phone": "+810000000000",
            "username": _USERNAME,
            "email": "admin@crafton.local",
            "user_type": "admin",
            "status": "approved",
            "display_name": "Administrator",
            "lang": "ja",
            "pw": hash_password(_PASSWORD),
        },
    )


def downgrade() -> None:
    op.get_bind().execute(
        text("DELETE FROM users WHERE username = :u"), {"u": _USERNAME}
    )
