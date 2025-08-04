# app/middleware/rate_limiting.py - Rate limiting middleware
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from loguru import logger
from typing import Callable

from app.core.tracing import get_current_trace_id


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Enhanced rate limiting middleware with OpenTelemetry trace context
    """

    def __init__(self, app, limiter: Limiter):
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next: Callable):
        try:
            response = await call_next(request)

            # Add rate limit headers if available
            if hasattr(request.state, "view_rate_limit"):
                response.headers["X-RateLimit-Limit"] = str(request.state.view_rate_limit)
                response.headers["X-RateLimit-Remaining"] = str(
                    getattr(request.state, "view_rate_limit_remaining", 0)
                )

            return response

        except RateLimitExceeded as e:
            client_ip = get_remote_address(request)
            trace_id = get_current_trace_id()

            logger.warning(f"🚫 Rate limit exceeded | ip={client_ip} | path={request.url.path}")

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {e.detail}",
                headers={
                    "Retry-After": str(e.retry_after),
                    "X-RateLimit-Limit": "0",
                    "X-RateLimit-Remaining": "0",
                    "X-Trace-ID": trace_id
                }
            )