"""Device tracking + revocation.

``touch_device`` is called on every authenticated request that carries an
``X-Device-Id`` header: it records/refreshes the device and rejects requests
from a revoked device (the practical equivalent of ending that session).
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import errors
from app.models.device import Device
from app.models.user import User

# Only rewrite last_seen_at when it's older than this, to avoid a DB write on
# every single request from an active device.
_FRESH = datetime.timedelta(minutes=5)


def touch_device(
    db: Session, user: User, device_id: str, label: str | None, now: datetime.datetime
) -> None:
    """Upsert the (user, device) row; 401 if the device has been revoked."""
    device_id = device_id[:64]
    label = label[:255] if label else None
    row = db.scalar(
        select(Device).where(
            Device.user_id == user.id, Device.device_id == device_id
        )
    )
    if row is not None:
        if row.revoked:
            raise errors.unauthorized("error.auth.device_revoked")
        if label and row.label != label:
            row.label = label
            db.commit()
        elif now - row.last_seen_at >= _FRESH:
            row.last_seen_at = now
            db.commit()
        return

    db.add(Device(user_id=user.id, device_id=device_id, label=label, last_seen_at=now))
    try:
        db.commit()
    except IntegrityError:
        # Concurrent first-touch of the same device — already inserted, fine.
        db.rollback()


def list_devices(db: Session, user: User) -> list[Device]:
    return list(
        db.scalars(
            select(Device)
            .where(Device.user_id == user.id)
            .order_by(Device.last_seen_at.desc())
        ).all()
    )


def revoke_device(db: Session, user: User, device_pk: uuid.UUID) -> Device:
    device = db.get(Device, device_pk)
    if device is None:
        raise errors.not_found()
    if device.user_id != user.id:
        raise errors.forbidden()
    device.revoked = True
    db.commit()
    db.refresh(device)
    return device


def list_all_devices(db: Session) -> list[Device]:
    """Admin view: every device across all users, most recently seen first."""
    return list(db.scalars(select(Device).order_by(Device.last_seen_at.desc())).all())
