"""System endpoints: liveness and readiness (no auth)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.db.session import get_db
from app.schemas.common import HealthResponse, ReadyResponse

router = APIRouter(tags=["system"])

_SERVICE = "crafton-api"


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """Liveness: the process is up. No dependencies checked."""
    return HealthResponse(status="ok", service=_SERVICE, version=__version__)


@router.get("/readyz", response_model=ReadyResponse)
def readyz(response: Response, db: Session = Depends(get_db)) -> ReadyResponse:
    """Readiness: can we reach the database? Returns 503 if not."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    overall = "ready" if db_status == "ok" else "not_ready"
    return ReadyResponse(status=overall, checks={"database": db_status})
