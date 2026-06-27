"""Job services: posting (with config-driven area/trade checks), search, lifecycle.

Service-area and allowed-trades enforcement are **config-driven and permissive
by default** (docs/07): `service_area_enforce` is off and `allowed_trades` is
empty out of the box, so nothing is restricted until an operator opts in.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import errors
from app.core.config import ConfigService
from app.models.contractor_profile import ContractorProfile
from app.models.enums import JobStatus
from app.models.job import Job
from app.models.user import User
from app.schemas.job import JobCreate, JobUpdate


def _check_service_area(prefecture: str, config: ConfigService) -> None:
    if not config.get_bool("service_area_enforce"):
        return
    allowed = config.get_list("service_area_prefectures")
    if allowed and prefecture not in allowed:
        raise errors.AppError(
            code="out_of_service_area",
            status_code=422,
            message_key="error.job.out_of_area",
        )


def _check_trades(trades: list[str], config: ConfigService) -> None:
    allowed = config.get_list("allowed_trades")
    if allowed and any(t not in allowed for t in trades):
        raise errors.AppError(
            code="trade_not_allowed",
            status_code=422,
            message_key="error.job.trade_not_allowed",
        )


def create_job(db: Session, contractor: User, payload: JobCreate, config: ConfigService) -> Job:
    _check_service_area(payload.prefecture, config)
    _check_trades(payload.trades, config)
    job = Job(
        contractor_id=contractor.id,
        trades=payload.trades,
        work_date=payload.work_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        prefecture=payload.prefecture,
        area=payload.area,
        address=payload.address,
        daily_wage=payload.daily_wage,
        headcount=payload.headcount,
        notes=payload.notes,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: uuid.UUID) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise errors.not_found()
    return job


def _require_owner(job: Job, contractor: User) -> None:
    if job.contractor_id != contractor.id:
        raise errors.forbidden()


def update_job(
    db: Session, contractor: User, job_id: uuid.UUID, payload: JobUpdate, config: ConfigService
) -> Job:
    job = get_job(db, job_id)
    _require_owner(job, contractor)
    if job.status is not JobStatus.OPEN:
        raise errors.conflict("job_not_editable", "error.job.not_editable")

    data = payload.model_dump(exclude_unset=True)
    if "prefecture" in data and data["prefecture"] is not None:
        _check_service_area(data["prefecture"], config)
    if "trades" in data and data["trades"] is not None:
        _check_trades(data["trades"], config)
    for field, value in data.items():
        setattr(job, field, value)

    db.commit()
    db.refresh(job)
    return job


def cancel_job(db: Session, contractor: User, job_id: uuid.UUID) -> Job:
    job = get_job(db, job_id)
    _require_owner(job, contractor)
    if job.status in (JobStatus.CLOSED, JobStatus.CANCELED):
        raise errors.conflict("job_not_cancelable", "error.job.not_cancelable")
    job.status = JobStatus.CANCELED
    db.commit()
    db.refresh(job)
    return job


def list_open_jobs(
    db: Session,
    *,
    trade: str | None = None,
    work_date: datetime.date | None = None,
    prefecture: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Job]:
    stmt = select(Job).where(Job.status == JobStatus.OPEN)
    if prefecture:
        stmt = stmt.where(Job.prefecture == prefecture)
    if work_date:
        stmt = stmt.where(Job.work_date == work_date)
    if trade:
        stmt = stmt.where(Job.trades.contains([trade]))  # postgres array @> [trade]
    stmt = stmt.order_by(Job.work_date.asc(), Job.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all())


def list_jobs_by_contractor(db: Session, contractor: User) -> list[Job]:
    return list(
        db.scalars(
            select(Job)
            .where(Job.contractor_id == contractor.id)
            .order_by(Job.created_at.desc())
        ).all()
    )


def company_name_for(db: Session, contractor_id: uuid.UUID) -> str | None:
    profile = db.get(ContractorProfile, contractor_id)
    return profile.company_name if profile else None
