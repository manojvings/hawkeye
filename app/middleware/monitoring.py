from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Histogram, Gauge
import time
from typing import Callable

# Prometheus metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint']
)

ACTIVE_REQUESTS = Gauge(
    'http_requests_active',
    'Active HTTP requests'
)


class MonitoringMiddleware(BaseHTTPMiddleware):
    """
    Prometheus monitoring middleware for metrics collection
    """

    async def dispatch(self, request: Request, call_next: Callable):
        # Get endpoint path template for better grouping
        endpoint = request.url.path
        method = request.method

        # Track active requests
        ACTIVE_REQUESTS.inc()

        start_time = time.time()

        try:
            response = await call_next(request)

            # Record metrics
            REQUEST_COUNT.labels(
                method=method,
                endpoint=endpoint,
                status=response.status_code
            ).inc()

            REQUEST_DURATION.labels(
                method=method,
                endpoint=endpoint
            ).observe(time.time() - start_time)

            return response

        except Exception as e:
            # Record error metrics
            REQUEST_COUNT.labels(
                method=method,
                endpoint=endpoint,
                status=500
            ).inc()

            REQUEST_DURATION.labels(
                method=method,
                endpoint=endpoint
            ).observe(time.time() - start_time)

            raise
        finally:
            # Decrease active requests
            ACTIVE_REQUESTS.dec()