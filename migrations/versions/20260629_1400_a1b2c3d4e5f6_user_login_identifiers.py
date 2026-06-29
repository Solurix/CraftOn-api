"""user login identifiers (username, email)

Adds the username/email login identifiers to ``users``. Phone stays the canonical
key; username + email are additional unique login handles (see ADR 0009).

Existing rows are backfilled with synthetic, unique values so the NOT NULL +
unique constraints can be applied without manual data fixes.

Revision ID: a1b2c3d4e5f6
Revises: 4cff8c3c9be6
Create Date: 2026-06-29 14:00:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = '4cff8c3c9be6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('username', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('email', sa.String(length=255), nullable=True))

    # Backfill any pre-existing rows with synthetic, unique values derived from
    # the (unique) primary key so the constraints below can be enforced.
    op.execute(
        """
        UPDATE users
           SET username = COALESCE(username, 'user_' || left(id::text, 8)),
               email = COALESCE(email, id::text || '@placeholder.local')
        """
    )

    op.alter_column('users', 'username', nullable=False)
    op.alter_column('users', 'email', nullable=False)
    op.create_unique_constraint('uq_users_username', 'users', ['username'])
    op.create_unique_constraint('uq_users_email', 'users', ['email'])


def downgrade() -> None:
    op.drop_constraint('uq_users_email', 'users', type_='unique')
    op.drop_constraint('uq_users_username', 'users', type_='unique')
    op.drop_column('users', 'email')
    op.drop_column('users', 'username')
