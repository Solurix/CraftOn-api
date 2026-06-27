"""Document upload & registration endpoints (docs/06)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_storage_service, require_roles
from app.core.storage import StorageService
from app.db.session import get_db
from app.models.enums import UserType
from app.models.user import User
from app.schemas.document import (
    DocumentOut,
    DocumentRegisterIn,
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
