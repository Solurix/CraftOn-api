"""FastAPI application factory.

Wires logging, the error envelope, CORS, the system endpoints (root), and the
versioned API (``/api/v1``). The OpenAPI schema served at ``/openapi.json`` is the
authoritative contract the web client generates types from (docs/06, docs/10).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.system import router as system_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging

API_V1_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="CRAFT-ON API",
        version=__version__,
        description=(
            "Backend for CRAFT-ON — on-demand spot matching for construction "
            "tradespeople in Japan (Phase 1 MVP). See the crafton repo docs."
        ),
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Tokens travel in the Authorization header (no cookies), so a permissive
    # CORS policy without credentials is safe for dev. Tighten origins in prod.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    # System endpoints live at the root; feature endpoints under /api/v1.
    app.include_router(system_router)
    app.include_router(api_router, prefix=API_V1_PREFIX)

    return app


app = create_app()
