"""Job services: posting (with config-driven area/trade checks), search, lifecycle.

Service-area and allowed-trades enforcement are **config-driven and permissive
by default** (docs/07): `service_area_enforce` is off and `allowed_trades` is
empty out of the box, so nothing is restricted until an operator opts in.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

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


def _check_photo_docs(db: Session, contractor: User, doc_ids: list[uuid.UUID]) -> None:
    """Attached photos must be the contractor's own `job_photo` documents —
    that's what makes them safely reusable across postings."""
    from app.models.document import Document
    from app.models.enums import DocType

    for doc_id in doc_ids:
        doc = db.get(Document, doc_id)
        if doc is None or doc.user_id != contractor.id or doc.doc_type is not DocType.JOB_PHOTO:
            raise errors.bad_request("invalid_photo", "error.job.invalid_photo")


def create_job(db: Session, contractor: User, payload: JobCreate, config: ConfigService) -> Job:
    _check_service_area(payload.prefecture, config)
    _check_trades(payload.trades, config)
    _check_photo_docs(db, contractor, payload.photo_doc_ids)
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
        photo_doc_ids=payload.photo_doc_ids,
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
    if data.get("photo_doc_ids") is None:
        data.pop("photo_doc_ids", None)
    else:
        _check_photo_docs(db, contractor, data["photo_doc_ids"])
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


def _job_ordering(sort: str | None) -> tuple[Any, ...]:
    """Map a sort key to ORDER BY columns; unknown keys fall back to soonest-first.

    Every ordering ends with the UUID primary key as a final, unique tiebreaker so
    the sort is total and limit/offset pagination is stable (no rows skipped or
    repeated across pages when the leading columns tie).
    """
    if sort == "wage_high":
        return (Job.daily_wage.desc(), Job.work_date.asc(), Job.id.asc())
    if sort == "wage_low":
        return (Job.daily_wage.asc(), Job.work_date.asc(), Job.id.asc())
    if sort == "new":
        return (Job.created_at.desc(), Job.id.asc())
    # default "date": soonest work date first, newest posting as tiebreaker
    return (Job.work_date.asc(), Job.created_at.desc(), Job.id.asc())


def list_open_jobs(
    db: Session,
    *,
    trade: str | None = None,
    work_date: datetime.date | None = None,
    prefecture: str | None = None,
    wage_min: int | None = None,
    wage_max: int | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    sort: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Job]:
    stmt = select(Job).where(Job.status == JobStatus.OPEN)
    if prefecture:
        stmt = stmt.where(Job.prefecture == prefecture)
    if work_date:
        stmt = stmt.where(Job.work_date == work_date)
    if date_from:
        stmt = stmt.where(Job.work_date >= date_from)
    if date_to:
        stmt = stmt.where(Job.work_date <= date_to)
    if wage_min is not None:
        stmt = stmt.where(Job.daily_wage >= wage_min)
    if wage_max is not None:
        stmt = stmt.where(Job.daily_wage <= wage_max)
    if trade:
        stmt = stmt.where(Job.trades.contains([trade]))  # postgres array @> [trade]
    stmt = stmt.order_by(*_job_ordering(sort)).limit(limit).offset(offset)
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
