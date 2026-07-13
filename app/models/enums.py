"""Domain enums shared across models, schemas, and services.

These are ``StrEnum`` so values serialize cleanly to JSON and compare to strings.
The corresponding PostgreSQL enum types store the **value** (e.g. ``"worker"``),
not the member name, via :func:`pg_enum`.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class UserType(StrEnum):
    WORKER = "worker"
    CONTRACTOR = "contractor"
    ADMIN = "admin"


class UserStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    SUSPENDED = "suspended"


class WorkerClass(StrEnum):
    EMPLOYEE = "employee"  # employed elsewhere, side job → day-labor employment
    FREELANCE = "freelance"  # 一人親方 / sole proprietor → subcontract


class DocType(StrEnum):
    PHOTO_ID = "photo_id"
    RESIDENCE_CARD_FRONT = "residence_card_front"
    RESIDENCE_CARD_BACK = "residence_card_back"
    QUALIFICATION = "qualification"
    INSURANCE_PROOF = "insurance_proof"
    JOB_PHOTO = "job_photo"


class DocReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class JobStatus(StrEnum):
    OPEN = "open"
    FILLED = "filled"
    CLOSED = "closed"
    CANCELED = "canceled"


class ApplicationStatus(StrEnum):
    APPLIED = "applied"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class MatchingStatus(StrEnum):
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    COMPLETED = "completed"
    CANCELED = "canceled"
    NOSHOW = "noshow"


class ContractType(StrEnum):
    EMPLOYMENT_DAYLABOR = "employment_daylabor"  # employee route
    SUBCONTRACT = "subcontract"  # freelance route


class FeeStatus(StrEnum):
    UNPAID = "unpaid"
    PAID = "paid"


class ReviewDirection(StrEnum):
    CONTRACTOR_TO_WORKER = "contractor_to_worker"
    WORKER_TO_CONTRACTOR = "worker_to_contractor"


class NotificationType(StrEnum):
    """In-app notification kinds. Stored as a varchar (not a DB enum) so new
    types don't need a migration; this enum is the known, rendered set."""

    APPLICATION_RECEIVED = "application_received"
    JOB_UPDATED = "job_updated"
    APPLICATION_CONFIRMED = "application_confirmed"
    APPLICATION_REJECTED = "application_rejected"
    WORKER_CHECKED_IN = "worker_checked_in"
    COMPLETION_REQUESTED = "completion_requested"
    COMPLETION_APPROVED = "completion_approved"
    REVIEW_RECEIVED = "review_received"
    ACCOUNT_APPROVED = "account_approved"
    ACCOUNT_REJECTED = "account_rejected"


def pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """Build a native PostgreSQL enum that stores member *values*.

    Using a stable ``name`` lets Alembic create/drop the type predictably.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [member.value for member in e],
    )
