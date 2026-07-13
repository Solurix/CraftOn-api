"""Job endpoints (docs/06). Posting is contractor-only; browsing is worker-only."""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import (
    approved_contractor,
    approved_worker,
    get_config,
    get_storage_service,
    require_approved,
)
from app.core.config import ConfigService
from app.core.storage import StorageService
from app.db.session import get_db
from app.models.job import Job
from app.models.user import User
from app.schemas.common import RESP_403_404
from app.schemas.job import JobCreate, JobOut, JobPhotoOut, JobUpdate
from app.services import documents, jobs, saved_jobs

router = APIRouter(tags=["jobs"])


def job_out(db: Session, job: Job) -> JobOut:
    out = JobOut.model_validate(job)
    out.contractor_company_name = jobs.company_name_for(db, job.contractor_id)
    return out


@router.post("/jobs", response_model=JobOut, status_code=201, responses=RESP_403_404)
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
    wage_min: int | None = Query(default=None, ge=0, description="JPY, inclusive"),
    wage_max: int | None = Query(default=None, ge=0, description="JPY, inclusive"),
    date_from: datetime.date | None = Query(default=None, description="work_date >= "),
    date_to: datetime.date | None = Query(default=None, description="work_date <= "),
    sort: Literal["date", "wage_high", "wage_low", "new"] = Query(default="date"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[JobOut]:
    found = jobs.list_open_jobs(
        db,
        trade=trade,
        work_date=work_date,
        prefecture=prefecture,
        wage_min=wage_min,
        wage_max=wage_max,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        limit=limit,
        offset=offset,
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


@router.put("/jobs/{job_id}/save", status_code=204, responses=RESP_403_404)
def save_job(
    job_id: uuid.UUID,
    user: User = Depends(approved_worker),
    db: Session = Depends(get_db),
) -> None:
    saved_jobs.save_job(db, user, job_id)


@router.delete("/jobs/{job_id}/save", status_code=204, responses=RESP_403_404)
def unsave_job(
    job_id: uuid.UUID,
    user: User = Depends(approved_worker),
    db: Session = Depends(get_db),
) -> None:
    saved_jobs.unsave_job(db, user, job_id)


@router.get("/jobs/{job_id}", response_model=JobOut, responses=RESP_403_404)
def get_job(
    job_id: uuid.UUID,
    user: User = Depends(require_approved),
    db: Session = Depends(get_db),
) -> JobOut:
    return job_out(db, jobs.get_job(db, job_id))


@router.patch("/jobs/{job_id}", response_model=JobOut, responses=RESP_403_404)
def update_job(
    job_id: uuid.UUID,
    payload: JobUpdate,
    user: User = Depends(approved_contractor),
    db: Session = Depends(get_db),
    config: ConfigService = Depends(get_config),
) -> JobOut:
    return job_out(db, jobs.update_job(db, user, job_id, payload, config))


@router.post("/jobs/{job_id}/cancel", response_model=JobOut, responses=RESP_403_404)
def cancel_job(
    job_id: uuid.UUID,
    user: User = Depends(approved_contractor),
    db: Session = Depends(get_db),
) -> JobOut:
    return job_out(db, jobs.cancel_job(db, user, job_id))


@router.get("/jobs/{job_id}/photos", response_model=list[JobPhotoOut], responses=RESP_403_404)
def job_photos(
    job_id: uuid.UUID,
    _viewer: User = Depends(require_approved),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> list[JobPhotoOut]:
    """Signed read URLs for a posting's attached photos. Any approved user who
    can see the job can see its photos (unlike private documents, which stay
    owner/admin-only)."""
    job = jobs.get_job(db, job_id)
    out: list[JobPhotoOut] = []
    for doc_id in job.photo_doc_ids:
        doc = documents.get_document(db, doc_id)
        if doc is None:
            continue
        out.append(JobPhotoOut(document_id=doc_id, read_url=documents.view_url(storage, doc)))
    return out
