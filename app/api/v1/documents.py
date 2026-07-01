"""Document upload, registration, listing & signed-read-URL endpoints (docs/06)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    get_storage_service,
    require_approved,
    require_roles,
)
from app.core import errors
from app.core.storage import StorageService
from app.db.session import get_db
from app.models.enums import UserType
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.document import (
    DocumentOut,
    DocumentRegisterIn,
    DocumentWithUrlOut,
    UploadUrlIn,
    UploadUrlOut,
)
from app.services import documents

router = APIRouter(tags=["documents"])

# Workers and contractors upload docs during onboarding (before approval).
_uploader = require_roles(UserType.WORKER, UserType.CONTRACTOR)


@router.post("/documents/upload-url", response_model=UploadUrlOut)
def create_upload_url(
    payload: UploadUrlIn,
    user: User = Depends(_uploader),
    storage: StorageService = Depends(get_storage_service),
) -> UploadUrlOut:
    ticket = documents.create_upload_ticket(storage, user, payload.doc_type, payload.content_type)
    return UploadUrlOut(
        upload_url=ticket.upload_url,
        storage_path=ticket.storage_path,
        method=ticket.method,
        headers=ticket.headers,
        expires_in=ticket.expires_in,
    )


@router.post("/documents", response_model=DocumentOut, status_code=201)
def register_document(
    payload: DocumentRegisterIn,
    user: User = Depends(_uploader),
    db: Session = Depends(get_db),
) -> DocumentOut:
    doc = documents.register_document(db, user, payload.doc_type, payload.storage_path)
    return DocumentOut.model_validate(doc)


@router.get("/documents/me", response_model=list[DocumentOut])
def list_my_documents(
    user: User = Depends(_uploader),
    db: Session = Depends(get_db),
) -> list[DocumentOut]:
    return [DocumentOut.model_validate(d) for d in documents.list_user_documents(db, user)]


@router.get(
    "/documents/{doc_id}/view-url",
    response_model=DocumentWithUrlOut,
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_document_view_url(
    doc_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> DocumentWithUrlOut:
    """Short-lived signed read URL for a document's bytes. The owner can view
    their own documents; admins can view any (vetting). The bytes are served by
    Cloud Storage via the signed URL — never proxied through the API."""
    doc = documents.get_document(db, doc_id)
    if doc is None:
        raise errors.not_found("error.document.not_found")
    if doc.user_id != user.id and user.user_type is not UserType.ADMIN:
        raise errors.forbidden()
    return DocumentWithUrlOut(
        **DocumentOut.model_validate(doc).model_dump(),
        read_url=documents.view_url(storage, doc),
    )


@router.get("/workers/{user_id}/photos", response_model=list[DocumentWithUrlOut])
def worker_public_photos(
    user_id: uuid.UUID,
    _viewer: User = Depends(require_approved),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> list[DocumentWithUrlOut]:
    """A worker's public portfolio photos (signed read URLs). Visible to any
    approved user — the same audience as the public worker profile. Only
    `job_photo` documents; identity documents are never exposed here."""
    docs = documents.list_public_worker_photos(db, user_id)
    return [
        DocumentWithUrlOut(
            **DocumentOut.model_validate(d).model_dump(),
            read_url=documents.view_url(storage, d),
        )
        for d in docs
    ]
