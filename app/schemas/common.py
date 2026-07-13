"""Shared response schemas (documented in OpenAPI)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """The uniform error envelope returned for non-2xx responses."""

    error: ErrorBody


# Shared ``responses=`` maps for route declarations so the documented error
# statuses aren't copy-pasted per router. All errors render the uniform envelope.
RESP_404: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse}}
RESP_403_404: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}
RESP_403_404_409: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, str]
