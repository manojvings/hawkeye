from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from loguru import logger


def setup_cors_middleware(app: FastAPI) -> None:
    """
    Configure CORS middleware with environment-specific settings
    """
    # Development vs Production CORS settings
    if settings.ENVIRONMENT == "development":
        # More permissive for development
        allowed_origins = settings.cors_origins_list + ["http://localhost:3000", "http://127.0.0.1:3000"]
        allow_credentials = True
    else:
        # Strict for production
        allowed_origins = settings.cors_origins_list
        allow_credentials = True

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Accept-Language",
            "Content-Language",
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "X-Request-ID",
            "X-Trace-ID"
        ],
        expose_headers=[
            "X-Request-ID",
            "X-Trace-ID",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining"
        ],
        max_age=600,  # Cache preflight requests for 10 minutes
    )

    logger.info(f"✅ CORS configured for {len(allowed_origins)} origins")