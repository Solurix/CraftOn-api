"""Notification endpoints (docs/06). Messages render to the caller's locale."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.i18n import translate
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.common import RESP_403_404
from app.schemas.notification import MarkAllReadOut, NotificationOut, UnreadCountOut
from app.services import notifications

router = APIRouter(tags=["notifications"])


def _render(n: Notification, locale: str) -> NotificationOut:
    params = n.params or {}
    return NotificationOut(
        id=n.id,
        type=n.type,
        title=translate(f"notification.{n.type}.title", locale, **params),
        body=translate(f"notification.{n.type}.body", locale, **params),
        link=n.link,
        is_read=n.is_read,
        created_at=n.created_at,
    )


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[NotificationOut]:
    rows = notifications.list_notifications(
        db, user, unread_only=unread_only, limit=limit, offset=offset
    )
    return [_render(n, user.preferred_language) for n in rows]


@router.get("/notifications/unread-count", response_model=UnreadCountOut)
def unread_count(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UnreadCountOut:
    return UnreadCountOut(count=notifications.unread_count(db, user))


@router.post("/notifications/read-all", response_model=MarkAllReadOut)
def read_all(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MarkAllReadOut:
    return MarkAllReadOut(updated=notifications.mark_all_read(db, user))


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut,
             responses=RESP_403_404)
def mark_read(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationOut:
    n = notifications.mark_read(db, user, notification_id)
    return _render(n, user.preferred_language)
