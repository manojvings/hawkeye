# app/middleware/tracing.py - Final request tracing middleware (with context propagation)
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger
import time
from slowapi.util import get_remote_address
from typing import Callable

# Import from core tracing
from app.core.tracing import get_current_trace_id
from opentelemetry import trace

class TracingMiddleware(BaseHTTPMiddleware):
    """
    Full-featured request tracing middleware
    - Creates and activates OpenTelemetry spans per request
    - Adds trace headers to all responses
    - Ensures trace/span context is active across exception handlers
    """

    def __init__(self, app, log_requests: bool = True, log_responses: bool = True):
        super().__init__(app)
        self.log_requests = log_requests
        self.log_responses = log_responses

    async def dispatch(self, request: Request, call_next: Callable):
        start_time = time.perf_counter()
        client_ip = get_remote_address(request)

        tracer = trace.get_tracer(__name__)

        # Activate span context using context manager
        with tracer.start_as_current_span(
            f"{request.method} {request.url.path}",
            attributes={
                "http.method": request.method,
                "http.url": str(request.url),
                "http.path": request.url.path,
                "http.client_ip": client_ip,
                "http.user_agent": request.headers.get("user-agent", "")[:100],  # truncate
            }
        ) as span:
            if self.log_requests:
                logger.info(f"🚀 {request.method} {request.url.path} | ip={client_ip}")

            try:
                response = await call_next(request)
                process_time = time.perf_counter() - start_time

                # Inject trace headers
                trace_id = get_current_trace_id()
                response.headers.update({
                    "X-Trace-ID": trace_id,
                    "X-Request-ID": trace_id
                })

                if span:
                    span.set_attribute("http.status_code", response.status_code)
                    span.set_attribute("http.response_time_ms", round(process_time * 1000, 2))

                    content_length = response.headers.get("content-length")
                    if content_length:
                        span.set_attribute("http.response_size", int(content_length))

                if self.log_responses:
                    status_emoji = "✅" if response.status_code < 400 else "❌"
                    logger.info(f"{status_emoji} {response.status_code} in {process_time:.3f}s")

                return response

            except Exception as e:
                process_time = time.perf_counter() - start_time

                if span:
                    span.record_exception(e)
                    span.set_attribute("error", True)
                    span.set_attribute("error.message", str(e)[:200])
                    span.set_attribute("error.type", type(e).__name__)

                logger.error(f"🔥 REQUEST FAILED: {str(e)} in {process_time:.3f}s")
                raise
