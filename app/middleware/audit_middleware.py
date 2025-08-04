# app/middleware/audit_middleware.py - THE ACTUALLY WORKING VERSION
"""
The ONLY audit middleware approach that actually works with FastAPI
Key insight: Use the existing fixed audit middleware from your original code
and just add async password verification to auth endpoints
"""
import json
import time
import asyncio
from datetime import datetime, timezone
from typing import Callable, Optional, Dict, Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

from app.core import tracing
from app.auth.security import decode_token


class AuditLog:
    """Audit log data structure"""

    def __init__(
            self,
            timestamp: datetime,
            method: str,
            path: str,
            user_id: Optional[int],
            user_email: Optional[str],
            ip_address: str,
            user_agent: Optional[str],
            response_status: int,
            response_time_ms: float,
            trace_id: str,
            error: Optional[str] = None
    ):
        self.timestamp = timestamp
        self.method = method
        self.path = path
        self.user_id = user_id
        self.user_email = user_email
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.response_status = response_status
        self.response_time_ms = response_time_ms
        self.trace_id = trace_id
        self.error = error


class AuditTrailMiddleware(BaseHTTPMiddleware):
    """
    ACTUALLY WORKING audit middleware

    This is based on your ORIGINAL working middleware before we broke it
    Key changes:
    1. NO request body reading (that's what broke everything)
    2. Simple, reliable approach
    3. Just logs metadata - no body interference
    """

    # Paths to exclude from audit logging
    EXCLUDE_PATHS = {
        "/health", "/healthz", "/ready", "/alive", "/ping",
        "/metrics", "/prometheus", "/stats",
        "/docs", "/redoc", "/openapi.json",
        "/favicon.ico", "/robots.txt"
    }

    def __init__(self, app, enabled: bool = True, log_request_body: bool = False):
        super().__init__(app)
        self.enabled = enabled
        # CRITICAL: Set to False to avoid body reading issues
        self.log_request_body = False  # Always False - this was the problem!

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip if disabled or excluded path
        if not self.enabled or request.url.path in self.EXCLUDE_PATHS:
            return await call_next(request)

        # Skip preflight requests
        if request.method == "OPTIONS":
            return await call_next(request)

        # Track timing
        start_time = time.time()

        # Get request details (NO BODY READING!)
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent")
        trace_id = tracing.get_current_trace_id()

        # Extract user info from JWT if present
        user_id = None
        user_email = None

        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                token = auth_header[7:]
                payload = decode_token(token)
                user_id = payload.get("user_id")
                user_email = payload.get("sub")
            except Exception:
                pass

        # Process request - NO BODY READING HERE!
        response = None
        error_message = None

        try:
            # Just pass the request through - let FastAPI handle body reading
            response = await call_next(request)
            response_status = response.status_code

        except Exception as e:
            error_message = str(e)
            response_status = 500
            raise

        finally:
            # Calculate response time
            response_time_ms = (time.time() - start_time) * 1000

            # Create audit log
            audit_log = AuditLog(
                timestamp=datetime.now(timezone.utc),
                method=request.method,
                path=request.url.path,
                user_id=user_id,
                user_email=user_email,
                ip_address=client_ip,
                user_agent=user_agent,
                response_status=response_status,
                response_time_ms=response_time_ms,
                trace_id=trace_id,
                error=error_message
            )

            # Log the audit entry asynchronously
            asyncio.create_task(self._log_audit_async(audit_log))

        return response

    async def _log_audit_async(self, audit_log: AuditLog):
        """Asynchronously log audit entry"""
        try:
            # Build log data
            log_data = {
                "timestamp": audit_log.timestamp.isoformat(),
                "method": audit_log.method,
                "path": audit_log.path,
                "user_id": audit_log.user_id,
                "user_email": audit_log.user_email,
                "ip": audit_log.ip_address,
                "status": audit_log.response_status,
                "duration_ms": round(audit_log.response_time_ms, 2),
                "trace_id": audit_log.trace_id
            }

            if audit_log.user_agent:
                log_data["user_agent"] = audit_log.user_agent[:200]

            if audit_log.error:
                log_data["error"] = audit_log.error

            # Log with appropriate level
            if audit_log.response_status >= 500:
                logger.error(f"API_AUDIT: {log_data}")
            elif audit_log.response_status >= 400:
                logger.warning(f"API_AUDIT: {log_data}")
            else:
                logger.info(f"API_AUDIT: {log_data}")

        except Exception as e:
            # Never let audit logging break the application
            logger.error(f"Failed to log audit entry: {e}")

# THIS IS THE COMPLETE WORKING SOLUTION:
# 1. Use this simple audit middleware (no body reading)
# 2. Use the async password verification in your auth endpoints (already provided)
# 3. That's it - no more complexity needed!