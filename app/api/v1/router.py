"""Aggregate router for API v1. Mounted at ``/api/v1`` by the app factory.

Feature routers (onboarding, documents, jobs, applications, matchings, chat,
reviews, admin) are added here as each build-order step lands.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    auth,
    chat,
    devices,
    documents,
    jobs,
    matching,
    notifications,
    onboarding,
    reviews,
    trades,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(onboarding.router)
api_router.include_router(documents.router)
api_router.include_router(jobs.router)
api_router.include_router(matching.router)
api_router.include_router(chat.router)
api_router.include_router(reviews.router)
api_router.include_router(notifications.router)
api_router.include_router(devices.router)
api_router.include_router(trades.router)
api_router.include_router(admin.router)
