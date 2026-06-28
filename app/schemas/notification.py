"""Notification schemas (title/body are rendered + localized at read time)."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    body: str
    link: str | None
    is_read: bool
    created_at: datetime.datetime


class UnreadCountOut(BaseModel):
    count: int


class MarkAllReadOut(BaseModel):
    updated: int
