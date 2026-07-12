"""Approve existing pending job photos.

Work photos are post-moderated (the only approval in the product is the
per-account vetting decision), so `pending` is meaningless for them: nothing
gates on it and — since user approval no longer blanket-reviews photos —
nothing would ever clear it. New photos register as `approved`; this backfills
the ones already stuck in `pending`.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-12 15:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE documents SET review_status = 'approved' "
            "WHERE doc_type = 'job_photo' AND review_status = 'pending'"
        )
    )


def downgrade() -> None:
    # Irreversible data fix: we can't tell which photos were pending before.
    # Reverting the status model change doesn't require undoing this backfill.
    pass
