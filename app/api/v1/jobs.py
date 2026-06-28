"""Job endpoints (docs/06). Posting is contractor-only; browsing is worker-only."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import (
    approved_contractor,
    approved_worker,
    get_config,
    require_approved,
)
from app.core.config import ConfigService
from app.db.session import get_db
from app.models.job import Job
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.job import JobCreate, JobOut, JobUpdate
from app.services import jobs, saved_jobs

router = APIRouter(tags=["jobs"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


def job_out(db: Session, job: Job) -> JobOut:
    out = JobOut.model_validate(job)
    out.contractor_company_name = jobs.company_name_for(db, job.contractor_id)
    return out


@router.post("/jobs", response_model=JobOut, status_code=201, responses=_ERRORS)
def create_job(
    payload: JobCreate,
    user: User = Depends(approved_contractor),
    db: Session = Depends(get_db),
    config: ConfigService = Depends(get_config),
) -> JobOut:
    job = jobs.create_job(db, user, payload, config)
    return job_out(db, job)


@router.get("/jobs", response_model=list[JobOut])
def search_jobs(
    user: User = Depends(approved_worker),
    db: Session = Depends(get_db),
    trade: str | None = Query(default=None),
    work_date: datetime.date | None = Query(default=None),
    prefecture: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[JobOut]:
    found = jobs.list_open_jobs(
        db, trade=trade, work_date=work_date, prefecture=prefecture, limit=limit, offset=offset
    )
    return [job_out(db, j) for j in found]


@router.get("/jobs/mine", response_model=list[JobOut])
def my_jobs(
    user: User = Depends(approved_contractor),
    db: Session = Depends(get_db),
) -> list[JobOut]:
    return [job_out(db, j) for j in jobs.list_jobs_by_contractor(db, user)]


# Saved/bookmarked jobs. These literal paths must be declared before the
# `/jobs/{job_id}` catch-all so they aren't parsed as a job id.
@router.get("/jobs/saved", response_model=list[JobOut])
def list_saved_jobs(
    user: User = Depends(approved_worker),
    db: Session = Depends(get_db),
) -> list[JobOut]:
    return [job_out(db, j) for j in saved_jobs.list_saved_jobs(db, user)]


@router.get("/jobs/saved-ids", response_model=list[uuid.UUID])
def list_saved_job_ids(
    user: User = Depends(approved_worker),
    db: Session = Depends(get_db),
) -> list[uuid.UUID]:
    return saved_jobs.saved_job_ids(db, user)


@router.put("/jobs/{job_id}/save", status_code=204, responses=_ERRORS)
def save_job(
    job_id: uuid.UUID,
    user: User = Depends(approved_worker),
    db: Session = Depends(get_db),
) -> None:
    saved_jobs.save_job(db, user, job_id)


@router.delete("/jobs/{job_id}/save", status_code=204, responses=_ERRORS)
def unsave_job(
    job_id: uuid.UUID,
    user: User = Depends(approved_worker),
    db: Session = Depends(get_db),
) -> None:
    saved_jobs.unsave_job(db, user, job_id)


@router.get("/jobs/{job_id}", response_model=JobOut, responses=_ERRORS)
def get_job(
    job_id: uuid.UUID,
    user: User = Depends(require_approved),
    db: Session = Depends(get_db),
) -> JobOut:
    return job_out(db, jobs.get_job(db, job_id))


@router.patch("/jobs/{job_id}", response_model=JobOut, responses=_ERRORS)
def update_job(
    job_id: uuid.UUID,
    payload: JobUpdate,
    user: User = Depends(approved_contractor),
    db: Session = Depends(get_db),
    config: ConfigService = Depends(get_config),
) -> JobOut:
    return job_out(db, jobs.update_job(db, user, job_id, payload, config))


@router.post("/jobs/{job_id}/cancel", response_model=JobOut, responses=_ERRORS)
def cancel_job(
    job_id: uuid.UUID,
    user: User = Depends(approved_contractor),
    db: Session = Depends(get_db),
) -> JobOut:
    return job_out(db, jobs.cancel_job(db, user, job_id))
