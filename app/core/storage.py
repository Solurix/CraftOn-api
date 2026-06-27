"""Document storage abstraction (Cloud Storage signed URLs).

Documents (IDs, residence cards, qualifications, job photos) live in Cloud
Storage; the API hands clients a signed **upload** URL and later a signed
**read** URL — the bytes never transit the API. Verification prefers derived
fields over hoarding images, and images are encrypted with least-privilege IAM
and a retention policy (docs/08).

Behind :class:`StorageService` so local/dev/CI/tests use :class:`FakeStorage`
(deterministic URLs, no GCP) while prod uses :class:`GcsStorage`. Selected by
``CRAFTON_STORAGE_MODE``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

from app.core.config import StorageMode, get_settings
from app.models.enums import DocType


@dataclass(frozen=True)
class UploadTicket:
    """Everything a client needs to PUT a file, plus the path to register after."""

    upload_url: str
    storage_path: str
    method: str
    headers: dict[str, str]
    expires_in: int


def build_object_path(user_id: uuid.UUID, doc_type: DocType) -> str:
    """Namespace objects by user and type; random suffix avoids collisions."""
    return f"users/{user_id}/{doc_type.value}/{uuid.uuid4().hex}"


class StorageService(Protocol):
    def create_upload_ticket(
        self, user_id: uuid.UUID, doc_type: DocType, content_type: str
    ) -> UploadTicket: ...

    def read_url(self, storage_path: str) -> str: ...


class FakeStorage:
    """Deterministic, offline storage for dev/CI/tests."""

    def __init__(self, bucket: str, ttl: int) -> None:
        self._bucket = bucket
        self._ttl = ttl

    def create_upload_ticket(
        self, user_id: uuid.UUID, doc_type: DocType, content_type: str
    ) -> UploadTicket:
        path = build_object_path(user_id, doc_type)
        return UploadTicket(
            upload_url=f"https://fake-storage.local/{self._bucket}/{path}?upload=1",
            storage_path=path,
            method="PUT",
            headers={"Content-Type": content_type},
            expires_in=self._ttl,
        )

    def read_url(self, storage_path: str) -> str:
        return f"https://fake-storage.local/{self._bucket}/{storage_path}?read=1"


class GcsStorage:
    """Real Cloud Storage v4 signed URLs (``google-cloud-storage`` lazy-imported)."""

    def __init__(self, bucket: str, ttl: int) -> None:
        self._bucket_name = bucket
        self._ttl = ttl
        self._client: Any = None

    def _bucket(self) -> Any:
        from google.cloud import storage

        if self._client is None:
            self._client = storage.Client()
        return self._client.bucket(self._bucket_name)

    def create_upload_ticket(
        self, user_id: uuid.UUID, doc_type: DocType, content_type: str
    ) -> UploadTicket:
        import datetime as _dt

        path = build_object_path(user_id, doc_type)
        blob = self._bucket().blob(path)
        url = blob.generate_signed_url(
            version="v4",
            expiration=_dt.timedelta(seconds=self._ttl),
            method="PUT",
            content_type=content_type,
        )
        return UploadTicket(
            upload_url=url,
            storage_path=path,
            method="PUT",
            headers={"Content-Type": content_type},
            expires_in=self._ttl,
        )

    def read_url(self, storage_path: str) -> str:
        import datetime as _dt

        blob = self._bucket().blob(storage_path)
        return blob.generate_signed_url(
            version="v4",
            expiration=_dt.timedelta(seconds=self._ttl),
            method="GET",
        )


@lru_cache
def get_storage() -> StorageService:
    settings = get_settings()
    if settings.storage_mode is StorageMode.GCS:
        return GcsStorage(settings.gcs_bucket, settings.signed_url_ttl_seconds)
    return FakeStorage(settings.gcs_bucket, settings.signed_url_ttl_seconds)
