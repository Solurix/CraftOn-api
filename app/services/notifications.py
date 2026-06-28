"""Notification services: create on events, list, mark read, unread count.

``notify()`` only adds to the session (no commit) so the notification is written
atomically with the event that triggered it — callers commit as usual.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import errors
from app.models.enums import NotificationType
from app.models.notification import Notification
from app.models.user import User


def notify(
    db: Session,
    user_id: uuid.UUID,
    type: NotificationType,
    *,
    params: dict[str, Any] | None = None,
    link: str | None = None,
) -> Notification:
    """Queue a notification for ``user_id`` (committed by the caller's txn)."""
    notification = Notification(
        user_id=user_id,
        type=type.value,
        params=params or {},
        link=link,
    )
    db.add(notification)
    return notification


def list_notifications(
    db: Session,
    user: User,
    *,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    stmt = stmt.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all())


def unread_count(db: Session, user: User) -> int:
    count = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
    )
    return int(count or 0)


def mark_read(db: Session, user: User, notification_id: uuid.UUID) -> Notification:
    notification = db.get(Notification, notification_id)
    if notification is None:
        raise errors.not_found()
    if notification.user_id != user.id:
        raise errors.forbidden()
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification


def mark_all_read(db: Session, user: User) -> int:
    unread = list(
        db.scalars(
            select(Notification).where(
                Notification.user_id == user.id, Notification.is_read.is_(False)
            )
        ).all()
    )
    for n in unread:
        n.is_read = True
    db.commit()
    return len(unread)
