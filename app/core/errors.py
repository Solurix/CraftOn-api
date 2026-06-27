"""Uniform error model and JSON envelope.

All API errors serialize to:

    { "error": { "code": "<machine_code>", "message": "<localized text>" } }

``AppError`` carries a stable machine ``code`` (for clients) and an i18n
``message_key`` (rendered to the caller's locale). Raise the factory helpers
(``unauthorized()``, ``forbidden()``, …) from route/service code.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.i18n import resolve_locale, translate


class AppError(Exception):
    """A domain/HTTP error with a machine code and a localizable message."""

    def __init__(
        self,
        *,
        code: str,
        status_code: int,
        message_key: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.message_key = message_key
        self.params = params or {}
        super().__init__(f"{code}: {message_key}")


# -- factory helpers -------------------------------------------------------

def unauthorized(message_key: str = "error.unauthorized", **params: Any) -> AppError:
    return AppError(
        code="unauthorized",
        status_code=status.HTTP_401_UNAUTHORIZED,
        message_key=message_key,
        params=params,
    )


def forbidden(message_key: str = "error.forbidden", **params: Any) -> AppError:
    return AppError(
        code="forbidden",
        status_code=status.HTTP_403_FORBIDDEN,
        message_key=message_key,
        params=params,
    )


def not_found(message_key: str = "error.not_found", **params: Any) -> AppError:
    return AppError(
        code="not_found",
        status_code=status.HTTP_404_NOT_FOUND,
        message_key=message_key,
        params=params,
    )


def bad_request(code: str, message_key: str, **params: Any) -> AppError:
    return AppError(
        code=code,
        status_code=status.HTTP_400_BAD_REQUEST,
        message_key=message_key,
        params=params,
    )


def conflict(code: str, message_key: str, **params: Any) -> AppError:
    return AppError(
        code=code,
        status_code=status.HTTP_409_CONFLICT,
        message_key=message_key,
        params=params,
    )


# -- rendering -------------------------------------------------------------

def _request_locale(request: Request) -> str:
    # ``request.state.locale`` is set by the auth dependency once a user is
    # known; otherwise negotiate from Accept-Language.
    preferred = getattr(request.state, "locale", None)
    return resolve_locale(request.headers.get("accept-language"), preferred)


def _envelope(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        locale = _request_locale(request)
        message = translate(exc.message_key, locale, **exc.params)
        return JSONResponse(
            status_code=exc.status_code, content=_envelope(exc.code, message)
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        locale = _request_locale(request)
        message = translate("error.validation", locale)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "validation_error",
                    "message": message,
                    # Field-level detail aids clients/devs; safe to expose.
                    "details": jsonable_encoder(exc.errors()),
                }
            },
        )
