"""Chat services. The POST path is the authoritative masking write path (docs/06)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ConfigService
from app.models.message import Message
from app.models.user import User
from app.services import matchings
from app.services.masking import mask_contact_info


def send_message(
    db: Session, user: User, matching_id: uuid.UUID, body: str, *, config: ConfigService
) -> Message:
    # Participant + existence check (raises 404/403).
    matchings.get_matching(db, user, matching_id)

    stored, was_filtered = body, False
    if config.flag("contact_mask_enabled"):
        result = mask_contact_info(body)
        stored, was_filtered = result.text, result.was_filtered

    message = Message(
        matching_id=matching_id,
        sender_id=user.id,
        body=stored,
        was_filtered=was_filtered,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def list_messages(db: Session, user: User, matching_id: uuid.UUID) -> list[Message]:
    matchings.get_matching(db, user, matching_id)
    return list(
        db.scalars(
            select(Message)
            .where(Message.matching_id == matching_id)
            .order_by(Message.created_at.asc())
        ).all()
    )
