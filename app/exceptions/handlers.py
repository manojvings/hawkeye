# app/exceptions/handlers.py
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi.util import get_remote_address
from app.core import tracing
import time


def get_safe_headers(request: Request) -> dict:
    """Extract and mask sensitive headers for logging"""
    headers = request.headers
    return {
        "user_agent": headers.get("user-agent", "unknown"),
        "authorization": (headers.get("authorization", "")[:10] + "...") if headers.get("authorization") else "none",
        "referer": headers.get("referer", "none")
    }


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    client_ip = get_remote_address(request)
    headers = get_safe_headers(request)

    tracing.error(
        f"🚨 HTTP {exc.status_code}: {exc.detail}",
        url=str(request.url),
        ip=client_ip,
        **headers
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "status_code": exc.status_code,
            "trace_id": tracing.get_current_trace_id(),
            "timestamp": time.time(),
            "path": request.url.path
        },
        headers=getattr(exc, 'headers', None)
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    client_ip = get_remote_address(request)
    headers = get_safe_headers(request)

    errors = [
        {
            "field": " -> ".join(str(x) for x in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        }
        for error in exc.errors()
    ]

    tracing.warning(
        f"⚠️ Validation error: {len(errors)} errors",
        url=str(request.url),
        ip=client_ip,
        **headers
    )

    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": errors,
            "trace_id": tracing.get_current_trace_id(),
            "timestamp": time.time()
        }
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    client_ip = get_remote_address(request)
    headers = get_safe_headers(request)

    tracing.error(
        f"🔥 UNHANDLED EXCEPTION: {str(exc)}",
        url=str(request.url),
        ip=client_ip,
        **headers
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "trace_id": tracing.get_current_trace_id(),
            "timestamp": time.time(),
            "error_type": type(exc).__name__
        }
    )


async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    client_ip = get_remote_address(request)
    headers = get_safe_headers(request)

    tracing.warning(
        f"🔍 HTTP {exc.status_code}: {exc.detail}",
        url=str(request.url),
        ip=client_ip,
        **headers
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "status_code": exc.status_code,
            "trace_id": tracing.get_current_trace_id(),
            "timestamp": time.time()
        }
    )
