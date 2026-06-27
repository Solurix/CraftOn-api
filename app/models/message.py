"""messages — in-app chat, keyed by matching. Stored AFTER the masking filter.

The contact-masking filter and the ``was_filtered`` audit flag are applied
server-side on write (authoritative). Chat may move to Firestore for real-time
delivery later; this row remains the audit record. See docs/08.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPKMixin


class Message(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "messages"

    matching_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matchings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)  # post-masking
    was_filtered: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
