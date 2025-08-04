# app/core/tracing.py - Complete implementation with local trace ID fallback

import os
import socket
import traceback
import sys
import json
import random
from datetime import datetime
from typing import Optional, Dict, Any
from loguru import logger
from contextvars import ContextVar

from app.core.config import settings

# Context variables for manual trace propagation
_trace_id_context: ContextVar[str] = ContextVar('trace_id', default='no-trace')
_span_id_context: ContextVar[str] = ContextVar('span_id', default='no-span')


# Local trace ID generation (works even without OpenTelemetry)
def generate_trace_id() -> str:
    """Generate a 128-bit trace ID as 32-character hex string"""
    return f"{random.getrandbits(128):032x}"


def generate_span_id() -> str:
    """Generate a 64-bit span ID as 16-character hex string"""
    return f"{random.getrandbits(64):016x}"


# OpenTelemetry imports with graceful fallback
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    # FIXED: Import from correct location in newer OpenTelemetry versions
    try:
        from opentelemetry.sdk.trace.sampling import AlwaysOnSampler
    except ImportError:
        # Fallback for older versions
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased as AlwaysOnSampler

        AlwaysOnSampler = lambda: AlwaysOnSampler(1.0)  # Sample everything

    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        OTLP_AVAILABLE = True
    except ImportError:
        OTLP_AVAILABLE = False

    OTEL_AVAILABLE = True

except ImportError as e:
    OTEL_AVAILABLE = False
    logger.error(f"❌ OpenTelemetry not available: {e}")

# Global tracer - initialized once at import time
_tracer = None
_tracer_provider = None


class TracingMiddleware:
    """Custom middleware to ensure trace context propagation - ALWAYS generates trace IDs"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # ALWAYS generate trace context for every request
            trace_id = None
            span_id = None

            # Try OpenTelemetry first (if available and enabled)
            if OTEL_AVAILABLE and settings.ENABLE_OTEL_EXPORTER:
                from opentelemetry import context as otel_context
                from opentelemetry.trace import get_current_span, set_span_in_context

                # Get the current span (created by FastAPI instrumentation)
                current_span = get_current_span()

                # Check if we have a valid span with actual trace data
                if (current_span and
                        hasattr(current_span, 'get_span_context') and
                        current_span.get_span_context().trace_id != 0):

                    span_context = current_span.get_span_context()
                    trace_id = f"{span_context.trace_id:032x}"
                    span_id = f"{span_context.span_id:016x}"

                    # Set in context vars (this is what gets used by our logging)
                    _trace_id_context.set(trace_id)
                    _span_id_context.set(span_id)

                    # Ensure the span is set in the OpenTelemetry context for the entire request
                    token = otel_context.attach(set_span_in_context(current_span))
                    try:
                        await self.app(scope, receive, send)
                    finally:
                        otel_context.detach(token)
                    return

                # If no valid span from FastAPI instrumentation, create our own
                elif _tracer:
                    path = scope.get("path", "unknown")
                    method = scope.get("method", "GET")
                    span_name = f"{method} {path}"

                    with _tracer.start_as_current_span(span_name) as span:
                        if span and hasattr(span, 'get_span_context'):
                            span_context = span.get_span_context()
                            if span_context.trace_id != 0:
                                trace_id = f"{span_context.trace_id:032x}"
                                span_id = f"{span_context.span_id:016x}"

                                _trace_id_context.set(trace_id)
                                _span_id_context.set(span_id)

                                # Add HTTP attributes
                                span.set_attribute("http.method", method)
                                span.set_attribute("http.url", path)
                                span.set_attribute("http.scheme", scope.get("scheme", "http"))

                        await self.app(scope, receive, send)
                    return

            # FALLBACK: Generate local trace IDs (always works)
            if not trace_id:
                trace_id = generate_trace_id()
                span_id = generate_span_id()

                # Set in context vars for the entire request
                _trace_id_context.set(trace_id)
                _span_id_context.set(span_id)

            await self.app(scope, receive, send)
        else:
            await self.app(scope, receive, send)


def setup_tracing(app, db_engine=None) -> bool:
    """Setup tracing - ALWAYS provides trace IDs (OpenTelemetry + local fallback)"""
    global _tracer, _tracer_provider

    # ALWAYS add our tracing middleware first (ensures trace IDs even if OTEL fails)
    app.add_middleware(TracingMiddleware)

    # ALWAYS setup structured logging
    setup_structured_logging(enable_json=settings.ENABLE_JSON_LOGGING)

    # Generate initial trace context for setup logging
    setup_trace_id = generate_trace_id()
    setup_span_id = generate_span_id()
    setup_logger = logger.bind(trace_id=setup_trace_id, span_id=setup_span_id)

    # Try to setup OpenTelemetry if available and enabled
    if not OTEL_AVAILABLE:
        setup_logger.warning("❌ OpenTelemetry not available - using local trace IDs only")
        return True  # Still successful - we have local tracing

    if not settings.ENABLE_OTEL_EXPORTER:
        setup_logger.info("📍 OpenTelemetry disabled in config - using local trace IDs only")
        return True  # Still successful - we have local tracing

    try:
        setup_logger.info("🔧 Setting up OpenTelemetry tracing...")

        # 1. Create Resource
        resource = Resource.create({
            SERVICE_NAME: "chawk-api",
            "service.version": "1.0.0",
            "service.environment": settings.ENVIRONMENT,
            "service.instance.id": f"chawk-api-{settings.ENVIRONMENT}"
        })

        # 2. Create TracerProvider with fixed sampling
        try:
            sampler = AlwaysOnSampler()
        except:
            # Fallback for different OpenTelemetry versions
            from opentelemetry.sdk.trace.sampling import DEFAULT_ON
            sampler = DEFAULT_ON

        _tracer_provider = TracerProvider(
            resource=resource,
            sampler=sampler
        )
        trace.set_tracer_provider(_tracer_provider)
        _tracer = trace.get_tracer(__name__)

        # 3. Setup Console Exporter (only if explicitly enabled)
        if settings.ENABLE_OTEL_CONSOLE_EXPORT:
            try:
                console_exporter = ConsoleSpanExporter()
                console_processor = BatchSpanProcessor(console_exporter)
                _tracer_provider.add_span_processor(console_processor)
                setup_logger.info("✅ Console span exporter enabled")
            except Exception as e:
                setup_logger.warning(f"⚠️ Console exporter failed: {e}")

        # 4. Optional External OTLP
        if settings.ENABLE_EXTERNAL_TRACING and OTLP_AVAILABLE:
            try:
                otlp_exporter = OTLPSpanExporter(
                    endpoint=settings.OTLP_ENDPOINT,
                    insecure=True
                )
                otlp_processor = BatchSpanProcessor(otlp_exporter)
                _tracer_provider.add_span_processor(otlp_processor)
                setup_logger.info(f"✅ OTLP exporter enabled: {settings.OTLP_ENDPOINT}")
            except Exception as e:
                setup_logger.warning(f"⚠️ OTLP exporter failed: {e}")

        # 5. Instrument FastAPI
        try:
            FastAPIInstrumentor.instrument_app(
                app,
                tracer_provider=_tracer_provider,
                excluded_urls="/health,/metrics,/docs,/redoc,/openapi.json"
            )
            setup_logger.info("✅ FastAPI instrumented")
        except Exception as e:
            setup_logger.warning(f"⚠️ FastAPI instrumentation failed: {e}")
            # Don't return False - we still have local tracing

        # 6. Instrument SQLAlchemy (if provided)
        if db_engine:
            instrument_database(db_engine)

        # 7. TEST TRACE CONTEXT with OpenTelemetry
        try:
            with _tracer.start_as_current_span("test_startup_span") as span:
                span.set_attribute("test", "startup")
                span.set_attribute("service", "chawk-api")
                test_trace_id, test_span_id = get_current_trace_span_ids()
                test_logger = logger.bind(trace_id=test_trace_id, span_id=test_span_id)
                test_logger.info(f"🧪 OpenTelemetry test: trace_id={test_trace_id}, span_id={test_span_id}")
        except Exception as e:
            setup_logger.warning(f"⚠️ OpenTelemetry test span failed: {e}")

        setup_logger.info("🎉 OpenTelemetry tracing setup complete")
        return True

    except Exception as e:
        error_logger = logger.bind(trace_id="setup-error", span_id="setup-error")
        error_logger.error(f"❌ OpenTelemetry setup failed: {e}")
        error_logger.exception("Full error details:")
        error_logger.info("📍 Falling back to local trace IDs only")
        # Still return True - we have local tracing working
        return True


def format_stack_trace(exception_info) -> Optional[str]:
    """Format exception stack trace for logging"""
    if not exception_info:
        return None

    try:
        if hasattr(exception_info, 'type') and hasattr(exception_info, 'traceback'):
            if exception_info.traceback:
                return ''.join(traceback.format_exception(
                    exception_info.type,
                    exception_info.value,
                    exception_info.traceback
                ))
        elif hasattr(exception_info, '__traceback__'):
            return ''.join(traceback.format_exception(
                type(exception_info),
                exception_info,
                exception_info.__traceback__
            ))
        return str(exception_info)
    except Exception:
        return "Error formatting stack trace"


def setup_structured_logging(enable_json: bool = None):
    """Enhanced structured logging with proper trace context propagation"""
    if enable_json is None:
        enable_json = settings.ENABLE_JSON_LOGGING

    logger.remove()

    # Get static context once
    hostname = socket.gethostname()
    pid = os.getpid()
    container_id = os.environ.get('HOSTNAME', hostname)[:12]
    environment = getattr(settings, 'ENVIRONMENT', 'development')

    if enable_json:
        def enhanced_json_sink(message):
            """Enhanced JSON sink with proper trace context"""
            record = message.record

            # Get trace context from the record's extra data (passed via bind())
            # This is more reliable than trying to access context vars from a different thread
            trace_id = record.get("extra", {}).get("trace_id", "no-trace")
            span_id = record.get("extra", {}).get("span_id", "no-span")

            # If not in extra, try to get from context vars as fallback
            if trace_id == "no-trace":
                try:
                    trace_id = _trace_id_context.get("no-trace")
                    span_id = _span_id_context.get("no-span")
                except:
                    trace_id, span_id = "no-trace", "no-span"

            # Enhanced log structure
            log_entry = {
                "@timestamp": datetime.utcnow().isoformat() + "Z",
                "level": record["level"].name,
                "message": record["message"],

                # SERVICE CONTEXT
                "service": {
                    "name": "chawk-api",
                    "version": "1.0.0",
                    "environment": environment,
                    "type": "api"
                },

                # INFRASTRUCTURE
                "host": {"hostname": hostname, "name": hostname},
                "process": {"pid": pid, "name": "uvicorn"},
                "container": {"id": container_id, "name": "chawk-api"},

                # CODE LOCATION
                "log": {
                    "origin": {
                        "file": {
                            "name": record["file"].name,
                            "line": record["line"],
                            "path": str(record["file"].path)
                        },
                        "function": record["function"]
                    },
                    "logger": record["name"]
                },

                # TRACING - Always include, even if no-trace
                "trace": {
                    "id": trace_id,
                    "span_id": span_id
                },

                # LABELS FOR FILTERING
                "labels": {
                    "service": "chawk-api",
                    "environment": environment,
                    "level": record["level"].name.lower(),
                    "module": record["module"],
                    "has_trace": "true" if trace_id != "no-trace" else "false"
                }
            }

            # Add extra fields from loguru bind() - EXCLUDE trace_id/span_id since we handled them above
            if hasattr(record, "extra") and record["extra"]:
                extra_filtered = {k: v for k, v in record["extra"].items()
                                  if k not in ["trace_id", "span_id"] and not k.startswith("_")}
                if extra_filtered:
                    log_entry["custom"] = extra_filtered

            # ENHANCED ERROR HANDLING
            if record["exception"]:
                stack_trace = format_stack_trace(record["exception"])
                log_entry["error"] = {
                    "type": record["exception"].type.__name__ if record["exception"].type else "UnknownError",
                    "message": str(record["exception"].value) if record["exception"].value else "Unknown error",
                    "category": "application_error",
                    "stack_trace": stack_trace,
                    "fingerprint": f"{record['file'].name}:{record['function']}:{record['line']}",
                    "location": {
                        "file": record["file"].name,
                        "function": record["function"],
                        "line": record["line"]
                    }
                }
                log_entry["labels"]["error_type"] = log_entry["error"]["type"]
                log_entry["labels"]["has_error"] = "true"

            # Output JSON
            try:
                json_line = json.dumps(log_entry, ensure_ascii=False, default=str)
                sys.stderr.write(json_line + "\n")
                sys.stderr.flush()
            except Exception as e:
                # Fallback to simple message if JSON serialization fails
                fallback = {
                    "@timestamp": datetime.utcnow().isoformat() + "Z",
                    "level": record["level"].name,
                    "message": str(record["message"]),
                    "error": f"JSON serialization failed: {e}"
                }
                sys.stderr.write(json.dumps(fallback) + "\n")
                sys.stderr.flush()

        logger.add(enhanced_json_sink, level=settings.LOG_LEVEL, enqueue=True, catch=True)
    else:
        # Human-readable format with trace context
        def format_with_trace(record):
            trace_id, span_id = get_current_trace_span_ids()
            if trace_id != "no-trace":
                trace_info = f" [trace:{trace_id[:8]}]"
            else:
                trace_info = ""

            return f"<green>{record['time']:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{record['level'].name: <8}</level> | <cyan>{record['name']}:{record['function']}:{record['line']}</cyan>{trace_info} - <level>{record['message']}</level>"

        logger.add(
            sys.stderr,
            format=format_with_trace,
            level=settings.LOG_LEVEL,
            colorize=True,
            enqueue=True,
            catch=True
        )


def instrument_database(db_engine) -> bool:
    """Add database instrumentation"""
    if not OTEL_AVAILABLE or not _tracer_provider:
        return False

    try:
        engine_to_instrument = getattr(db_engine, 'sync_engine', db_engine)
        SQLAlchemyInstrumentor().instrument(
            engine=engine_to_instrument,
            tracer_provider=_tracer_provider,
            enable_commenter=True
        )
        # Use bound logger for database instrumentation logs
        trace_id, span_id = get_current_trace_span_ids()
        db_logger = logger.bind(trace_id=trace_id, span_id=span_id)
        db_logger.info("✅ SQLAlchemy instrumented")
        return True
    except Exception as e:
        trace_id, span_id = get_current_trace_span_ids()
        db_logger = logger.bind(trace_id=trace_id, span_id=span_id)
        db_logger.warning(f"⚠️ SQLAlchemy instrumentation failed: {e}")
        return False


def get_current_trace_span_ids() -> tuple[str, str]:
    """Get current trace_id and span_id - ALWAYS returns valid IDs"""

    # Method 1: Context variables are most reliable (set by our middleware)
    try:
        trace_id = _trace_id_context.get()
        span_id = _span_id_context.get()
        if trace_id != "no-trace" and span_id != "no-span":
            return trace_id, span_id
    except:
        pass

    # Method 2: Try OpenTelemetry current span (fallback)
    if OTEL_AVAILABLE and settings.ENABLE_OTEL_EXPORTER:
        try:
            from opentelemetry.trace import get_current_span

            current_span = get_current_span()

            if (current_span is not None and
                    hasattr(current_span, 'get_span_context')):

                span_context = current_span.get_span_context()

                # Only use if it's a valid, non-zero context
                if (span_context and
                        hasattr(span_context, 'trace_id') and
                        hasattr(span_context, 'span_id') and
                        span_context.trace_id != 0 and
                        span_context.span_id != 0):

                    trace_id = f"{span_context.trace_id:032x}"
                    span_id = f"{span_context.span_id:016x}"

                    # Cache in context vars for faster subsequent access
                    try:
                        _trace_id_context.set(trace_id)
                        _span_id_context.set(span_id)
                    except:
                        pass

                    return trace_id, span_id

        except Exception:
            pass

    # Method 3: Generate local trace IDs if nothing else works
    trace_id = generate_trace_id()
    span_id = generate_span_id()

    # Cache the generated IDs
    try:
        _trace_id_context.set(trace_id)
        _span_id_context.set(span_id)
    except:
        pass

    return trace_id, span_id


def set_trace_context(trace_id: str, span_id: str):
    """Manually set trace context - useful for async operations"""
    _trace_id_context.set(trace_id)
    _span_id_context.set(span_id)


def get_current_trace_id() -> str:
    """Get current trace ID"""
    trace_id, _ = get_current_trace_span_ids()
    return trace_id


def get_current_span_id() -> str:
    """Get current span ID"""
    _, span_id = get_current_trace_span_ids()
    return span_id


def get_trace_context() -> Dict[str, str]:
    """Get trace context"""
    trace_id, span_id = get_current_trace_span_ids()
    return {"trace_id": trace_id, "span_id": span_id}


def create_span(name: str, attributes: Optional[Dict] = None):
    """Create a new OpenTelemetry span with context propagation"""
    if not OTEL_AVAILABLE or not _tracer:
        return None

    try:
        span = _tracer.start_span(name)
        if attributes:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(str(key), str(value))

        # Update context vars when creating new spans
        if hasattr(span, 'get_span_context'):
            span_context = span.get_span_context()
            if span_context and span_context.is_valid:
                trace_id = f"{span_context.trace_id:032x}"
                span_id = f"{span_context.span_id:016x}"
                _trace_id_context.set(trace_id)
                _span_id_context.set(span_id)

        return span
    except Exception as e:
        logger.warning(f"Failed to create span '{name}': {e}")
        return None


def log_with_trace(level: str, message: str, **kwargs):
    """Enhanced logging with automatic trace context - ALWAYS includes trace context"""
    trace_id, span_id = get_current_trace_span_ids()

    # ALWAYS bind trace context, even if it's "no-trace"
    # This ensures the JSON sink gets the trace info from the record
    extra_data = {
        "trace_id": trace_id,
        "span_id": span_id,
        **kwargs
    }

    # Use Loguru's bind() to add structured data
    try:
        log_func = getattr(logger.bind(**extra_data), level.lower())
        log_func(message)
    except AttributeError:
        logger.error(f"Invalid log level: {level}")


def log_error_with_context(message: str, exception: Exception = None, **kwargs):
    """Log error with full context and stack trace"""
    error_context = {
        "event_type": "error",
        **kwargs
    }

    if exception:
        logger.bind(**error_context).exception(message)
    else:
        log_with_trace("error", message, **error_context)


# Convenience functions
def info(message: str, **kwargs):
    """Log info with trace context"""
    log_with_trace("info", message, **kwargs)


def debug(message: str, **kwargs):
    """Log debug with trace context"""
    log_with_trace("debug", message, **kwargs)


def warning(message: str, **kwargs):
    """Log warning with trace context"""
    log_with_trace("warning", message, **kwargs)


def error(message: str, **kwargs):
    """Log error with trace context"""
    log_with_trace("error", message, **kwargs)


# Export for use in other modules
__all__ = [
    'setup_tracing', 'get_current_trace_span_ids', 'get_current_trace_id', 'get_current_span_id',
    'get_trace_context', 'set_trace_context', 'create_span', 'log_with_trace', 'log_error_with_context',
    'info', 'debug', 'warning', 'error'
]