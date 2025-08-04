# app/main.py - Complete implementation with proper tracing setup
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
import time
import asyncio

# Core imports
from app.core.config import settings
from app.db.database import get_db, init_db, engine, AsyncSessionLocal

# Import tracing
from app.core import tracing

# Import API routes
from app.api.v1.endpoints import auth, users
from app.api.v1.endpoints import organizations

# Import middleware
from app.middleware.security import SecurityHeadersMiddleware
from app.middleware.cors import setup_cors_middleware
from app.middleware.rate_limiting import RateLimitMiddleware
from app.middleware.monitoring import MonitoringMiddleware
from app.middleware.audit_middleware import AuditTrailMiddleware
from app.middleware.compression import CompressionMiddleware

# Import exception handlers
from app.exceptions.handlers import (
    http_exception_handler,
    validation_exception_handler,
    global_exception_handler,
    starlette_http_exception_handler
)

# Import token cleanup
from app.db.crud.token import cleanup_expired_tokens

# Rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"]
)

# Global variable to track tracing status
tracing_enabled = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan with database initialization and cleanup
    """
    tracing.info("CHawk API startup initiated")

    # Initialize database
    try:
        await init_db()
        tracing.info("Database initialized successfully")
    except Exception as e:
        tracing.error(f"Database initialization failed: {e}")
        raise

    # Start background token cleanup task
    cleanup_task = asyncio.create_task(periodic_token_cleanup())

    # Log startup configuration
    tracing.info(f"Environment: {settings.ENVIRONMENT}")
    tracing.info(f"Log Level: {settings.LOG_LEVEL}")
    tracing.info(f"Tracing: {'Enabled' if tracing_enabled else 'Disabled'}")
    tracing.info(f"Rate Limiting: {'Enabled' if settings.RATE_LIMIT_ENABLED else 'Disabled'}")
    tracing.info(f"CORS Origins: {len(settings.cors_origins_list)} configured")

    tracing.info("CHawk API v1.0.0 startup complete")

    yield

    # Cleanup
    tracing.info("CHawk API shutdown initiated")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    tracing.info("CHawk API shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="CHawk API",
    description="Enterprise-grade FastAPI with comprehensive security and monitoring",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT == "development" else None
)

# =============================================================================
# TRACING SETUP - WORKS WITH YOUR CONFIG
# =============================================================================

# Always setup tracing - uses OpenTelemetry when enabled, local IDs as fallback
try:
    tracing_enabled = tracing.setup_tracing(app, engine)
    if tracing_enabled:
        if settings.ENABLE_OTEL_EXPORTER:
            tracing.info("✅ Tracing with OpenTelemetry enabled")
        else:
            tracing.info("✅ Local tracing enabled (OpenTelemetry disabled)")
    else:
        tracing.warning("⚠️ Tracing setup encountered issues")
except Exception as e:
    tracing.error(f"❌ Failed to initialize tracing: {e}")
    tracing_enabled = False

# =============================================================================
# MIDDLEWARE SETUP (Order matters!)
# =============================================================================

tracing.info("Configuring middleware pipeline...")

# 1. Compression (early in pipeline for response compression)
app.add_middleware(
    CompressionMiddleware,
    minimum_size=1024,
    compression_level=6,
    exclude_paths=['/metrics', '/health']
)
tracing.info("✅ Compression middleware added - automatic gzip/brotli compression")

# 2. Monitoring (Prometheus metrics)
app.add_middleware(MonitoringMiddleware)

# 3. Security Headers (protects all responses)
app.add_middleware(SecurityHeadersMiddleware)

# 4. CORS (handles preflight requests)
setup_cors_middleware(app)

# 5. Audit Trail (automatic logging of all API access)
app.add_middleware(
    AuditTrailMiddleware,
    enabled=True,
    log_request_body=True
)
tracing.info("✅ Audit trail middleware added - automatic API access logging")

# 6. Rate Limiting
app.add_middleware(RateLimitMiddleware, limiter=limiter)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# NOTE: TracingMiddleware is now added automatically by setup_tracing()
# No need to add it manually here

tracing.info("Middleware pipeline configured")

# =============================================================================
# EXCEPTION HANDLERS
# =============================================================================

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# =============================================================================
# PROMETHEUS METRICS
# =============================================================================

instrumentator = Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    should_group_untemplated=False,
    should_instrument_requests_inprogress=True,
    inprogress_labels=True
)
instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

# =============================================================================
# API ROUTES
# =============================================================================

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(organizations.router, prefix="/api/v1/organizations", tags=["Organizations"])

tracing.info("API routes configured")


# =============================================================================
# SYSTEM ENDPOINTS
# =============================================================================

@app.get("/health", tags=["System"])
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Comprehensive health check with database connectivity test
    """
    try:
        # Test database connection
        await db.execute("SELECT 1")

        health_data = {
            "status": "healthy",
            "service": "CHawk API",
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT,
            "timestamp": time.time(),
            "trace_id": tracing.get_current_trace_id(),
            "checks": {
                "database": "connected",
                "tracing": "enabled" if tracing_enabled else "disabled",
                "rate_limiting": "enabled" if settings.RATE_LIMIT_ENABLED else "disabled"
            }
        }

        tracing.info("Health check passed",
                     endpoint="/health",
                     status="success",
                     database_status="connected")
        return health_data

    except Exception as e:
        tracing.error(f"Health check failed: {e}",
                      endpoint="/health",
                      status="failed",
                      error_type=type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unhealthy - database connection failed"
        )


@app.get("/", tags=["System"])
async def api_information():
    """API information endpoint"""
    api_info = {
        "message": "CHawk API - Enterprise FastAPI with Enhanced Security & Monitoring",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "status": "operational",
        "trace_id": tracing.get_current_trace_id(),
        "features": {
            "authentication": "JWT with refresh tokens and blacklisting",
            "security": "Rate limiting, CORS, security headers",
            "observability": "OpenTelemetry tracing, Prometheus metrics, structured logging"
        },
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "authentication": "/api/v1/auth",
            "users": "/api/v1/users",
            "documentation": "/docs" if settings.ENVIRONMENT == "development" else "Contact administrator"
        },
        "timestamp": time.time()
    }

    tracing.info("API information requested",
                 endpoint="/",
                 status="success")
    return api_info


# Development-only debug endpoints
if settings.ENVIRONMENT == "development":
    @app.get("/debug/trace", tags=["Debug"])
    async def debug_trace_context():
        """Debug endpoint to inspect current trace context"""
        trace_info = {
            "current_trace_id": tracing.get_current_trace_id(),
            "current_span_id": tracing.get_current_span_id(),
            "trace_context": tracing.get_trace_context(),
            "message": "Current trace context",
            "timestamp": time.time(),
            "tracing_enabled": tracing_enabled,
            "otel_available": hasattr(tracing, 'OTEL_AVAILABLE') and tracing.OTEL_AVAILABLE
        }

        tracing.info("Debug trace context accessed",
                     endpoint="/debug/trace",
                     trace_data=trace_info)
        return trace_info

    @app.get("/debug/test-log", tags=["Debug"])
    async def debug_test_logging():
        """Test endpoint to verify logging and tracing"""
        trace_id = tracing.get_current_trace_id()
        span_id = tracing.get_current_span_id()

        # Test different log levels
        tracing.debug("Debug message from test endpoint", test_type="debug")
        tracing.info("Info message from test endpoint", test_type="info")
        tracing.warning("Warning message from test endpoint", test_type="warning")

        # Test structured logging
        tracing.info("Structured log test",
                     user_id=12345,
                     action="test_logging",
                     metadata={"key": "value", "number": 42})

        response = {
            "message": "Logging test completed",
            "trace_id": trace_id,
            "span_id": span_id,
            "logs_generated": ["debug", "info", "warning", "structured"],
            "timestamp": time.time()
        }

        tracing.info("Logging test completed successfully", response_data=response)
        return response


# =============================================================================
# BACKGROUND TASKS
# =============================================================================

async def periodic_token_cleanup():
    """Background task for token cleanup using batch operations"""
    while True:
        try:
            async with AsyncSessionLocal() as db:
                stats = await cleanup_expired_tokens(db, batch_size=1000)
                tracing.info("Token cleanup completed",
                             cleanup_stats=stats,
                             task="periodic_cleanup")
        except Exception as e:
            tracing.error(f"Token cleanup failed: {e}",
                          task="periodic_cleanup",
                          error_type=type(e).__name__)

        # Run every hour
        await asyncio.sleep(3600)


# Final initialization log
tracing.info("CHawk API fully initialized with enterprise-grade features!")
tracing.info("Ready for production traffic with comprehensive security and monitoring!")