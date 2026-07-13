"""Small builders for test request payloads + shared API test helpers.

Shared by the integration test modules so the standard onboarding payloads,
unique phone numbers, and the job → apply → confirm → complete chains are
written once. Pure-unit test files don't use any of this.
"""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

# ``approved_member`` fixture signature (see tests/conftest.py).
Member = Callable[..., tuple[dict[str, str], str]]

# Standard onboarding payloads.
CONTRACTOR = {"company_name": "ABC", "contact_person": "S", "prefecture": "Tokyo"}
WORKER = {"nationality": "JP", "worker_class": "employee", "trades": ["大工"]}
EMPLOYEE = WORKER  # alias: an employee-class JP worker

# Standard job posting (override fields per test as needed).
JOB: dict[str, Any] = {
    "trades": ["大工"], "work_date": "2026-07-01",
    "start_time": "08:00:00", "end_time": "17:00:00",
    "prefecture": "Tokyo", "daily_wage": 18000, "headcount": 1,
}

# Unique within a test run; tables are truncated between tests, so cross-file
# collisions cannot happen. Starts in a +819055… range disjoint from the
# hardcoded +8190123…/+8190000… phones used by auth-focused tests.
_phone_counter = itertools.count(55_000_001)


def unique_phone() -> str:
    return f"+8190{next(_phone_counter):08d}"


def post_job(client: TestClient, contractor_headers: dict[str, str], **over: Any) -> str:
    resp = client.post("/api/v1/jobs", json={**JOB, **over}, headers=contractor_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def apply_to_job(client: TestClient, worker_headers: dict[str, str], job_id: str) -> str:
    resp = client.post(f"/api/v1/jobs/{job_id}/apply", headers=worker_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def confirm_matching(
    client: TestClient,
    contractor_headers: dict[str, str],
    worker_headers: dict[str, str],
    **job_over: Any,
) -> str:
    """Post a job, apply as the worker, confirm — return the matching id."""
    job_id = post_job(client, contractor_headers, **job_over)
    app_id = apply_to_job(client, worker_headers, job_id)
    resp = client.post(f"/api/v1/applications/{app_id}/confirm", headers=contractor_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def confirmed_matching(
    client: TestClient, approved_member: Member, **job_over: Any
) -> tuple[dict[str, str], dict[str, str], str]:
    """The standard contractor → worker → job → apply → confirm chain.

    Returns ``(contractor_headers, worker_headers, matching_id)``.
    """
    ch, _ = approved_member("contractor", unique_phone(), onboard=CONTRACTOR)
    wh, _ = approved_member("worker", unique_phone(), onboard=WORKER)
    return ch, wh, confirm_matching(client, ch, wh, **job_over)


def complete_matching(
    client: TestClient,
    contractor_headers: dict[str, str],
    worker_headers: dict[str, str],
    **job_over: Any,
) -> str:
    """Drive a fresh matching to ``completed`` — return the matching id."""
    mid = confirm_matching(client, contractor_headers, worker_headers, **job_over)
    client.post(f"/api/v1/matchings/{mid}/check-in", headers=worker_headers)
    client.post(f"/api/v1/matchings/{mid}/complete-request", headers=worker_headers)
    client.post(f"/api/v1/matchings/{mid}/approve-completion", headers=contractor_headers)
    return mid


def signup_payload(**overrides: Any) -> dict[str, Any]:
    """A ``POST /auth/session`` registration body with unique credentials.

    Registration now requires username/email/password; this fills them with
    collision-free values so callers only specify what the test cares about
    (role, display_name, …).
    """
    handle = "u" + uuid.uuid4().hex[:12]
    body: dict[str, Any] = {
        "username": handle,
        "email": f"{handle}@test.local",
        "password": "test-password-123",
    }
    body.update(overrides)
    return body
