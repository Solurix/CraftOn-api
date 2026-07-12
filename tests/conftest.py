"""Pytest fixtures.

Deterministic by design: fake auth (no GCP/network) and an ephemeral Postgres
schema. Set ``CRAFTON_TEST_DATABASE_URL`` to target a dedicated DB; otherwise
``CRAFTON_DATABASE_URL`` is used. The schema is created fresh for the test
session and every table is truncated between tests for isolation.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator

# Configure the environment BEFORE importing app modules (settings read env once).
os.environ.setdefault("CRAFTON_ENV", "ci")
os.environ.setdefault("CRAFTON_AUTH_MODE", "fake")
os.environ.setdefault(
    "CRAFTON_DATABASE_URL",
    "postgresql+psycopg://crafton:crafton@localhost:5432/crafton",
)
if "CRAFTON_TEST_DATABASE_URL" in os.environ:
    os.environ["CRAFTON_DATABASE_URL"] = os.environ["CRAFTON_TEST_DATABASE_URL"]
# Disable the check-in time window for the shared fixtures (factories post jobs
# on fixed dates, so real "now" is outside the shift). The window itself is
# exercised in tests/test_checkin_window.py, which re-enables it and freezes
# the clock — same pattern as approved_member bypassing vetting.
os.environ.setdefault("CRAFTON_CFG__CHECKIN_OPEN_MINUTES_BEFORE_START", "0")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

import app.models  # noqa: E402,F401 — register tables on Base.metadata
from app.core.auth import make_fake_token  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402

get_settings.cache_clear()

# Tables in dependency order for TRUNCATE (CASCADE handles the rest anyway).
_ALL_TABLES = (
    "messages",
    "reviews",
    "matchings",
    "applications",
    "jobs",
    "documents",
    "worker_profiles",
    "contractor_profiles",
    "app_config",
    "users",
)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    eng = create_engine(get_settings().database_url, future=True)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture(autouse=True)
def _clean_tables(engine: Engine) -> Iterator[None]:
    yield
    with engine.begin() as conn:
        conn.execute(
            text(f"TRUNCATE TABLE {', '.join(_ALL_TABLES)} RESTART IDENTITY CASCADE")
        )


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    from app.main import app

    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def _override_get_db() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> Callable[..., dict[str, str]]:
    """Return a builder for an ``Authorization`` header with a fake token."""

    def _build(phone_number: str = "+819012345678", **extra: object) -> dict[str, str]:
        return {"Authorization": f"Bearer {make_fake_token(phone_number, **extra)}"}

    return _build


@pytest.fixture
def approved_member(
    client: TestClient, db: Session, auth_headers: Callable[..., dict[str, str]]
) -> Callable[..., tuple[dict[str, str], str]]:
    """Sign up a worker/contractor, optionally onboard, and mark them approved.

    Returns ``(auth_headers, user_id)``. Bypasses admin vetting for setup speed;
    the gate itself is exercised in test_vetting_visa_gate.
    """
    import uuid as _uuid

    from app.models.enums import UserStatus
    from app.models.user import User

    def _make(
        role: str, phone: str, *, onboard: dict | None = None
    ) -> tuple[dict[str, str], str]:
        headers = auth_headers(phone)
        handle = "u" + phone.lstrip("+")
        resp = client.post(
            "/api/v1/auth/session",
            json={
                "user_type": role,
                "display_name": role.title(),
                "username": handle,
                "email": f"{handle}@test.local",
                "password": "test-password-123",
            },
            headers=headers,
        )
        assert resp.status_code in (200, 201), resp.text
        user_id = resp.json()["user"]["id"]
        if onboard is not None:
            path = f"/api/v1/onboarding/{role}"
            onb = client.post(path, json=onboard, headers=headers)
            assert onb.status_code == 200, onb.text
        user = db.get(User, _uuid.UUID(user_id))
        assert user is not None
        user.status = UserStatus.APPROVED
        db.commit()
        return headers, user_id

    return _make


@pytest.fixture
def seed_admin(db: Session) -> Callable[..., dict[str, str]]:
    """Seed an approved admin (not self-assignable via API) and return its headers."""
    from app.core import security
    from app.models.enums import UserStatus, UserType
    from app.models.user import User

    def _seed(phone_number: str = "+818000000001") -> dict[str, str]:
        handle = "admin" + phone_number.lstrip("+")
        user = User(
            phone_number=phone_number,
            username=handle,
            email=f"{handle}@test.local",
            user_type=UserType.ADMIN,
            status=UserStatus.APPROVED,
            display_name="Admin",
            password_hash=security.hash_password("admin-password"),
        )
        db.add(user)
        db.commit()
        return {"Authorization": f"Bearer {make_fake_token(phone_number)}"}

    return _seed
