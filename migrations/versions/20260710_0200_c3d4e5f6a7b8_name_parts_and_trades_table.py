"""worker name parts + admin-managed trades catalog

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-10 02:00:00+00:00

- worker_profiles gains structured name parts (family/given/middle); the
  display-oriented full_name is composed from them on write.
- New ``trades`` table: the curated trade catalog with multilingual labels
  (ja canonical stored value + en label), admin-managed. Seeded with the
  trades that were previously hardcoded in the web picker.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED = [
    ("大工", "Carpenter"),
    ("鳶", "Scaffolder (tobi)"),
    ("電気工", "Electrician"),
    ("配管", "Plumber"),
    ("内装", "Interior finisher"),
    ("左官", "Plasterer"),
    ("塗装", "Painter"),
    ("鉄筋", "Rebar worker"),
    ("型枠", "Formwork carpenter"),
    ("解体", "Demolition"),
    ("重機オペレーター", "Heavy equipment operator"),
    ("土工", "Groundwork laborer"),
]


def upgrade() -> None:
    op.add_column(
        "worker_profiles", sa.Column("family_name", sa.String(length=120), nullable=True)
    )
    op.add_column(
        "worker_profiles", sa.Column("given_name", sa.String(length=120), nullable=True)
    )
    op.add_column(
        "worker_profiles", sa.Column("middle_name", sa.String(length=120), nullable=True)
    )

    trades = op.create_table(
        "trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name_ja", sa.String(length=120), nullable=False),
        sa.Column("name_en", sa.String(length=120), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trades")),
        sa.UniqueConstraint("name_ja", name=op.f("uq_trades_name_ja")),
    )
    op.bulk_insert(
        trades,
        [
            {
                "id": uuid.uuid4(),
                "name_ja": ja,
                "name_en": en,
                "active": True,
                "sort_order": i,
            }
            for i, (ja, en) in enumerate(_SEED)
        ],
    )


def downgrade() -> None:
    op.drop_table("trades")
    op.drop_column("worker_profiles", "middle_name")
    op.drop_column("worker_profiles", "given_name")
    op.drop_column("worker_profiles", "family_name")
