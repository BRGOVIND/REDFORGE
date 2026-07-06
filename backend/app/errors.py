"""Standardized API error responses.

Every error — expected (HTTP) or unexpected — is returned in one shape::

    { "success": false, "error": { "code": "...", "message": "...", "details": ... } }

Unexpected exceptions are logged with a full traceback server-side but never
leak internals to the client; they return a safe generic message.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging_config import get_logger

logger = get_logger("api")

_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
}


def _code_for(status: int) -> str:
    return _STATUS_CODES.get(status, "error" if status < 500 else "internal_error")


def error_response(
    status: int, code: str, message: str, details: Optional[Any] = None
) -> JSONResponse:
    # jsonable_encoder makes arbitrary detail payloads (e.g. validation error
    # contexts holding exception objects) safely serializable.
    return JSONResponse(
        status_code=status,
        content=jsonable_encoder(
            {"success": False, "error": {"code": code, "message": message, "details": details}}
        ),
    )


async def _http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    # String details are safe user-facing messages; dict/other go into `details`.
    message = detail if isinstance(detail, str) else "Request failed"
    details = None if isinstance(detail, str) else detail
    return error_response(exc.status_code, _code_for(exc.status_code), message, details)


async def _validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(422, "validation_error", "Request validation failed", exc.errors())


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.log(
        logging.ERROR,
        f"unhandled error on {request.method} {request.url.path}: {exc!r}",
        exc_info=exc,
    )
    return error_response(500, "internal_error", "An internal error occurred")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
