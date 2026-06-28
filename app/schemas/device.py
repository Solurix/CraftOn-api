"""Device schemas."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    device_id: str
    label: str | None
    last_seen_at: datetime.datetime
    revoked: bool
    created_at: datetime.datetime
    # Populated only in admin listings.
    user_display_name: str | None = None
