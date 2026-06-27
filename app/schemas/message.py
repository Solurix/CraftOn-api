"""Chat message schemas."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    matching_id: uuid.UUID
    sender_id: uuid.UUID
    body: str  # stored after masking
    was_filtered: bool
    created_at: datetime.datetime
