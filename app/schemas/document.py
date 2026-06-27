"""Document schemas: signed upload URL request + registration + read view."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import DocReviewStatus, DocType


class UploadUrlIn(BaseModel):
    doc_type: DocType
    content_type: str = "application/octet-stream"


class UploadUrlOut(BaseModel):
    upload_url: str
    storage_path: str
    method: str
    headers: dict[str, str]
    expires_in: int


class DocumentRegisterIn(BaseModel):
    doc_type: DocType
    storage_path: str


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doc_type: DocType
    review_status: DocReviewStatus
    review_note: str | None
    created_at: datetime.datetime


class DocumentWithUrlOut(DocumentOut):
    """Document plus a signed read URL (admin vetting / owner view)."""

    read_url: str
