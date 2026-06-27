"""Document services: issue signed upload URLs, register, and list."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.storage import StorageService, UploadTicket
from app.models.document import Document
from app.models.enums import DocType
from app.models.user import User


def create_upload_ticket(
    storage: StorageService, user: User, doc_type: DocType, content_type: str
) -> UploadTicket:
    return storage.create_upload_ticket(user.id, doc_type, content_type)


def register_document(
    db: Session, user: User, doc_type: DocType, storage_path: str
) -> Document:
    doc = Document(user_id=user.id, doc_type=doc_type, storage_path=storage_path)
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
