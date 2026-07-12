"""Application & confirmation services.

Confirm is the heart of matching: it runs the compliance gates, routes the
contract type from the worker class, snapshots the wage, records the configured
platform fee as owed, and creates the matching in ``confirmed``.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import errors
from app.core.config import ConfigService
from app.models.application import Application
from app.models.contractor_profile import ContractorProfile
from app.models.enums import (
    ApplicationStatus,
    FeeStatus,
    JobStatus,
    MatchingStatus,
    NotificationType,
)
from app.models.job import Job
from app.models.matching import Matching
from app.models.user import User
from app.models.worker_profile import WorkerProfile
from app.services import compliance, notifications, terms


def apply_to_job(db: Session, worker: User, job_id: uuid.UUID) -> Application:
    job = db.get(Job, job_id)
    if job is None:
        raise errors.not_found()
    if job.status is not JobStatus.OPEN:
        raise errors.conflict("job_not_open", "error.application.job_not_open")

    existing = db.scalar(
        select(Application).where(
            Application.job_id == job_id, Application.worker_id == worker.id
        )
    )
    if existing is not None:
        raise errors.conflict("already_applied", "error.application.already_applied")

    application = Application(job_id=job_id, worker_id=worker.id)
    db.add(application)
    notifications.notify(
        db,
        job.contractor_id,
        NotificationType.APPLICATION_RECEIVED,
        params={"name": worker.display_name},
        link=f"/my-jobs/{job.id}",
    )
    db.commit()
    db.refresh(application)
    return application


def _owned_application(
    db: Session, contractor: User, application_id: uuid.UUID
) -> tuple[Application, Job]:
    application = db.get(Application, application_id)
    if application is None:
        raise errors.not_found()
    job = db.get(Job, application.job_id)
    if job is None or job.contractor_id != contractor.id:
        raise errors.forbidden()
    return application, job


def list_applicants(db: Session, contractor: User, job_id: uuid.UUID) -> list[Application]:
    job = db.get(Job, job_id)
    if job is None:
        raise errors.not_found()
    if job.contractor_id != contractor.id:
        raise errors.forbidden()
    return list(
        db.scalars(
            select(Application)
            .where(Application.job_id == job_id)
            .order_by(Application.created_at.asc())
        ).all()
    )


def confirm_application(
    db: Session,
    contractor: User,
    application_id: uuid.UUID,
    *,
    config: ConfigService,
    today: datetime.date,
) -> Matching:
    application, job = _owned_application(db, contractor, application_id)
    if application.status is not ApplicationStatus.APPLIED:
        raise errors.conflict("application_not_pending", "error.application.not_pending")

    profile = db.get(WorkerProfile, application.worker_id)
    if profile is None:
        raise errors.bad_request("onboarding_incomplete", "error.onboarding.not_completed")

    # Compliance gates: visa (non-JP) + freelance insurance.
    compliance.check_confirmable(db, profile, today=today, config=config)

    contract_type = terms.contract_type_for(profile.worker_class)
    platform_fee = config.get_int("platform_fee_per_match")

    matching = Matching(
        job_id=job.id,
        worker_id=application.worker_id,
        application_id=application.id,
        status=MatchingStatus.CONFIRMED,
        contract_type=contract_type,
        daily_wage=job.daily_wage,  # snapshot of agreed wage
        platform_fee=platform_fee,  # configured fee, owed on completion
        fee_status=FeeStatus.UNPAID,
    )
    db.add(matching)
    db.flush()  # populate matching.id for the notification link
    application.status = ApplicationStatus.CONFIRMED

    # Mark the job filled once headcount is met. The matching we just added is
    # flushed above, so it is already included in this count — do not add it again.
    confirmed_count = db.scalar(
        select(func.count())
        .select_from(Matching)
        .where(Matching.job_id == job.id, Matching.status != MatchingStatus.CANCELED)
    )
    if (confirmed_count or 0) >= job.headcount:
        job.status = JobStatus.FILLED

    company = db.get(ContractorProfile, job.contractor_id)
    notifications.notify(
        db,
        application.worker_id,
        NotificationType.APPLICATION_CONFIRMED,
        params={
            "company": company.company_name if company else "",
            "date": job.work_date.isoformat(),
        },
        link=f"/matchings/{matching.id}",
    )

    db.commit()
    db.refresh(matching)
    return matching


def reject_application(db: Session, contractor: User, application_id: uuid.UUID) -> Application:
    application, _job = _owned_application(db, contractor, application_id)
    if application.status is not ApplicationStatus.APPLIED:
        raise errors.conflict("application_not_pending", "error.application.not_pending")
    application.status = ApplicationStatus.REJECTED
    notifications.notify(
        db,
        application.worker_id,
        NotificationType.APPLICATION_REJECTED,
        link="/applications",
    )
    db.commit()
    db.refresh(application)
    return application


def withdraw_application(db: Session, worker: User, application_id: uuid.UUID) -> Application:
    application = db.get(Application, application_id)
    if application is None:
        raise errors.not_found()
    if application.worker_id != worker.id:
        raise errors.forbidden()
    if application.status is not ApplicationStatus.APPLIED:
        raise errors.conflict("application_not_pending", "error.application.not_pending")
    application.status = ApplicationStatus.WITHDRAWN
    db.commit()
    db.refresh(application)
    return application


def list_my_applications(db: Session, worker: User) -> list[Application]:
    return list(
        db.scalars(
            select(Application)
            .where(Application.worker_id == worker.id)
            .order_by(Application.created_at.desc())
        ).all()
    )
