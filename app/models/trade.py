"""trades — the curated, admin-managed trade catalog (multilingual labels).

Worker profiles and jobs keep storing trades as plain strings (the Japanese
canonical name, ``name_ja``); this table drives the pickers, provides the
English label, and lets admins merge free-text entries into canonical ones.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Trade(TimestampMixin, Base):
    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Canonical stored value (what worker_profiles.trades / jobs.trades contain).
    name_ja: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    name_en: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
