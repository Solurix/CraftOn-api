"""Compliance gates — the hard MVP rules (docs/08).

Two gates, both config-toggleable but ON by default:

* **Visa gate** (`visa_gate_enabled`): a non-Japanese worker cannot be *approved*
  or *confirmed* without residence-card front+back on file AND a non-expired
  visa. Manual admin check in Phase 1; the schema supports P2 automation.
* **Freelance-insurance gate** (`require_freelance_insurance`): an uninsured
  一人親方 (freelance) cannot be *confirmed*.

These raise :class:`AppError` (422) with machine codes and i18n message keys so
the failure reaches the client as a localized, actionable message.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy.orm import Session

from app.core import errors
from app.core.config import ConfigService
from app.models.document import Document
from app.models.enums import DocReviewStatus, WorkerClass
from app.models.worker_profile import WorkerProfile

JAPAN = "JP"


def _gate_error(code: str, message_key: str) -> errors.AppError:
    return errors.AppError(
        code=code,
        status_code=422,
        message_key=message_key,
    )


def _card_doc_usable(db: Session, doc_id: uuid.UUID) -> bool:
    """A residence-card document counts only if it exists and wasn't rejected
    by an admin — a rejected card is no card (docs/08)."""
    doc = db.get(Document, doc_id)
    return doc is not None and doc.review_status is not DocReviewStatus.REJECTED


def check_visa_gate(
    db: Session, profile: WorkerProfile, *, today: datetime.date, config: ConfigService
) -> None:
    """Raise if a non-JP worker lacks card + valid visa (when the gate is on)."""
    if not config.flag("visa_gate_enabled"):
        return
    if (profile.nationality or "").upper() == JAPAN:
        return
    if not (profile.residence_card_front_doc_id and profile.residence_card_back_doc_id):
        raise _gate_error("visa_card_required", "error.visa.card_required")
    if not (
        _card_doc_usable(db, profile.residence_card_front_doc_id)
        and _card_doc_usable(db, profile.residence_card_back_doc_id)
    ):
        raise _gate_error("visa_card_required", "error.visa.card_required")
    if profile.visa_expiry_date is None:
        raise _gate_error("visa_expiry_required", "error.visa.expiry_required")
    if profile.visa_expiry_date < today:
        raise _gate_error("visa_expired", "error.visa.expired")


def check_freelance_insurance_gate(
    profile: WorkerProfile, *, config: ConfigService
) -> None:
    """Raise if an uninsured freelance worker is being confirmed (when the gate is on)."""
    if not config.get_bool("require_freelance_insurance"):
        return
    if profile.worker_class is WorkerClass.FREELANCE and not profile.has_insurance:
        raise _gate_error("freelance_insurance_required", "error.insurance.freelance_required")


def check_confirmable(
    db: Session, profile: WorkerProfile, *, today: datetime.date, config: ConfigService
) -> None:
    """All gates that must pass before a worker can be confirmed for a job."""
    check_visa_gate(db, profile, today=today, config=config)
    check_freelance_insurance_gate(profile, config=config)
