import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from fastapi import HTTPException
from app.core import tracing as logger
from app.core.config import settings

# Configure logging for SQLAlchemy (ORM logs only)
logging.basicConfig()
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

# SQLAlchemy Engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=0,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={
        "server_settings": {
            "application_name": "chawk_api"
        },
        # ✅ CORRECT parameters for asyncpg:
        "command_timeout": 5,      # Command execution timeout
        # Remove "connect_timeout" - not supported by asyncpg
    }
)

# Async session factory
AsyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Declarative base class
Base = declarative_base()


async def init_db():
    """Initialize database tables with trace-aware logging."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error("Database initialization failed", error=str(e), type=type(e).__name__)
        raise


async def get_db():
    """Async session dependency with trace-aware error logging."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            # Better error logging for FastAPI-specific exceptions
            if isinstance(e, HTTPException):
                logger.error(
                    "Database session error",
                    error=e.detail or str(e),
                    type=type(e).__name__,
                    status_code=e.status_code
                )
            else:
                logger.error(
                    "Database session error",
                    error=str(e),
                    type=type(e).__name__
                )
            await session.rollback()
            raise
        finally:
            await session.close()
