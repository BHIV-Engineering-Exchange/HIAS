"""
Security & Middleware Module
T-GOV-F02 Remediation & Hardening for HIAS Architecture
Implements comprehensive error boundary protection, standardized exception handlers,
and security headers to guarantee zero unhandled 500 exceptions on malformed inputs.
"""
from __future__ import annotations

import uuid
from typing import Callable
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware


class ErrorBoundaryMiddleware(BaseHTTPMiddleware):
    """
    Middleware that captures all uncaught exceptions in the request pipeline.
    Prevents crash dumps or raw tracebacks from escaping, ensuring strict error boundary protection.
    """

    async def dispatch(self, request: Request, call_next: Callable):
        trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
        try:
            response = await call_next(request)
            response.headers["X-Trace-ID"] = trace_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            return response
        except Exception as exc:
            # Complete error boundary protection: zero unhandled crashes
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "InternalServerError",
                    "detail": "An internal error occurred, captured by the error boundary.",
                    "trace_id": trace_id,
                    "error_type": type(exc).__name__,
                },
                headers={
                    "X-Trace-ID": trace_id,
                    "X-Content-Type-Options": "nosniff",
                }
            )


def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Standardized handler for Pydantic RequestValidationErrors.
    Returns HTTP 422 Unprocessable Entity with normalized detail list.
    """
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "ValidationError",
            "detail": exc.errors(),
            "trace_id": trace_id,
        },
        headers={"X-Trace-ID": trace_id}
    )


def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    Standardized handler for HTTPExceptions.
    """
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTPException",
            "detail": exc.detail,
            "trace_id": trace_id,
        },
        headers={"X-Trace-ID": trace_id}
    )


def install_security_middlewares(app: FastAPI) -> None:
    """
    Installs error boundary protection, exception handlers, and security headers on the FastAPI app.
    """
    app.add_middleware(ErrorBoundaryMiddleware)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
