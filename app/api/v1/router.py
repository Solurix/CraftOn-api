"""Aggregate router for API v1. Mounted at ``/api/v1`` by the app factory.

Feature routers (onboarding, documents, jobs, applications, matchings, chat,
reviews, admin) are added here as each build-order step lands.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth

api_router = APIRouter()
api_router.include_router(auth.router)
