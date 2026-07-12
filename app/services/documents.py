"""Document services: issue signed upload URLs, register, list, and view."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.storage import StorageService, UploadTicket
from app.models.document import Document
from app.models.enums import DocReviewStatus, DocType
from app.models.user import User


def create_upload_ticket(
    storage: StorageService, user: User, doc_type: DocType, content_type: str
) -> UploadTicket:
    return storage.create_upload_ticket(user.id, doc_type, content_type)


def register_document(
    db: Session, user: User, doc_type: DocType, storage_path: str
) -> Document:
    doc = Document(user_id=user.id, doc_type=doc_type, storage_path=storage_path)
    # Work photos are post-moderated, not review-gated: the only approval in the
    # product is the per-account vetting decision. They're born approved and an
    # admin can still reject (= hide) an inappropriate one later.
    if doc_type is DocType.JOB_PHOTO:
        doc.review_status = DocReviewStatus.APPROVED
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def list_user_documents(db: Session, user: User) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.user_id == user.id)
            .order_by(Document.created_at.desc())
        ).all()
    )


def get_document(db: Session, doc_id: uuid.UUID) -> Document | None:
    return db.get(Document, doc_id)


def list_public_worker_photos(db: Session, user_id: uuid.UUID) -> list[Document]:
    """A worker's portfolio photos for their public profile: `job_photo` documents
    that haven't been rejected. Portfolio images are post-moderated (shown, then
    removable), unlike identity documents which are strictly gated (docs/08)."""
    return list(
        db.scalars(
            select(Document)
            .where(
                Document.user_id == user_id,
                Document.doc_type == DocType.JOB_PHOTO,
                Document.review_status != DocReviewStatus.REJECTED,
            )
            .order_by(Document.created_at.desc())
        ).all()
    )


def view_url(storage: StorageService, doc: Document) -> str:
    """A short-lived signed read URL for a document's bytes (never via the API)."""
    return storage.read_url(doc.storage_path)
