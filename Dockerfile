# Ultimate Production-Ready Minimal Dockerfile for CHawk API
# Incorporates expert feedback for true production deployment
# Target: <200MB with enterprise security and performance

# ================================
# Stage 1: Builder (Dependencies)
# ================================
FROM python:3.12-slim as builder

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    POETRY_VERSION=1.7.1

# Install only essential build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && pip install --no-cache-dir poetry==$POETRY_VERSION \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy Poetry files (strict poetry.lock for production consistency)
COPY pyproject.toml poetry.lock README.md ./

# Export requirements and build wheel files for faster, more reliable installs
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes --only=main \
    && pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements.txt

# ================================
# Stage 2: Production Runtime
# ================================
FROM python:3.12-slim as runtime

# Production metadata
LABEL org.opencontainers.image.title="CHawk API" \
      org.opencontainers.image.description="Production CHawk API - Ultra Minimal & Secure" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.vendor="TekSecur" \
      org.opencontainers.image.authors="TekSecur Development Team" \
      org.opencontainers.image.source="https://github.com/your-org/chawk-api"

# Production environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    ENVIRONMENT=production \
    WORKERS=2

# Install ONLY runtime dependencies (no build tools)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc/* /usr/share/man/* /var/cache/apt/*

# Create non-root user with security best practices
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --no-create-home --shell /bin/false app

# Set working directory
WORKDIR /app

# Copy wheels from builder and install with optimal flags
COPY --from=builder /build/wheels /tmp/wheels
COPY --from=builder /build/requirements.txt /tmp/requirements.txt

# Install dependencies from pre-built wheels (faster, more secure)
RUN pip install --no-cache-dir --no-index --find-links /tmp/wheels \
        -r /tmp/requirements.txt gunicorn==21.2.0 \
    && rm -rf /tmp/wheels /tmp/requirements.txt \
    && pip cache purge

# Copy application code with proper ownership
COPY --chown=app:app . .

# Create Python package structure and set secure permissions
RUN find /app -name "*.pyc" -delete \
    && find /app -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true \
    && mkdir -p /app/logs \
    && chmod -R 755 /app \
    && chown -R app:app /app

# Switch to non-root user for security
USER app

# Health check with proper configuration
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Production command with Gunicorn for optimal performance and reliability
# Using UvicornWorker for async support with multiple workers
CMD ["gunicorn", "app.main:app", \
     "--workers", "2", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info", \
     "--worker-tmp-dir", "/dev/shm", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--timeout", "30", \
     "--keep-alive", "5"]