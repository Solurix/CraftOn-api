"""Device endpoints: list/revoke your own devices; admin sees all (docs/06)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import admin_user, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import RESP_403_404
from app.schemas.device import DeviceOut
from app.services import devices, onboarding

router = APIRouter(tags=["devices"])


@router.get("/me/devices", response_model=list[DeviceOut])
def my_devices(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DeviceOut]:
    return [DeviceOut.model_validate(d) for d in devices.list_devices(db, user)]


@router.post(
    "/me/devices/{device_id}/revoke", response_model=DeviceOut, responses=RESP_403_404
)
def revoke_my_device(
    device_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeviceOut:
    return DeviceOut.model_validate(devices.revoke_device(db, user, device_id))


@router.get("/admin/devices", response_model=list[DeviceOut])
def admin_list_devices(
    _admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> list[DeviceOut]:
    rows = devices.list_all_devices(db)
    users = onboarding.list_users_by_ids(db, [d.user_id for d in rows])
    out: list[DeviceOut] = []
    for d in rows:
        item = DeviceOut.model_validate(d)
        owner = users.get(d.user_id)
        item.user_display_name = owner.display_name if owner else None
        out.append(item)
    return out
