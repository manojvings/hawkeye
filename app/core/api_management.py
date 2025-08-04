# app/core/api_management.py
"""
Base API management system for all endpoints
Provides rate limiting, API key auth, and permissions as a base layer
"""
from typing import Optional, List
from functools import wraps
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, APIKeyHeader
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
import secrets
from app.db.database import get_db
from app.core import tracing
from app.db.models import APIKey

# Global rate limiter instance
rate_limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    headers_enabled=True
)

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class APIManagement:
    """
    Central API management for rate limiting and authentication
    """

    # Default rate limits by operation type
    DEFAULT_RATE_LIMITS = {
        "read": "100/minute",
        "write": "30/minute",
        "delete": "10/minute",
        "auth": "5/minute",
        "admin": "20/minute"
    }

    @staticmethod
    def rate_limit(limit: Optional[str] = None, operation_type: str = "read"):
        """
        Decorator for rate limiting endpoints

        Usage:
            @router.get("/users")
            @APIManagement.rate_limit(operation_type="read")
            async def list_users():
                ...
        """

        def decorator(func):
            # Use provided limit or default based on operation type
            rate_limit_value = limit or APIManagement.DEFAULT_RATE_LIMITS.get(
                operation_type,
                APIManagement.DEFAULT_RATE_LIMITS["read"]
            )

            # Apply rate limiter
            @rate_limiter.limit(rate_limit_value)
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Log rate limit application
                request = kwargs.get('request')
                if request:
                    tracing.debug(
                        f"Rate limit applied: {rate_limit_value}",
                        endpoint=request.url.path,
                        operation_type=operation_type
                    )
                return await func(*args, **kwargs)

            return wrapper

        return decorator

    @staticmethod
    async def get_api_key(
            api_key: Optional[str] = Depends(api_key_header),
            db: AsyncSession = Depends(get_db)
    ) -> Optional[APIKey]:
        """
        Validate API key and return key object
        """
        if not api_key:
            return None

        # Hash the API key for comparison
        from app.auth.security import Hasher
        key_hash = Hasher.get_password_hash(api_key)

        # Look up API key
        from sqlalchemy import select
        result = await db.execute(
            select(APIKey).where(
                APIKey.key_hash == key_hash,
                APIKey.is_active == True
            )
        )

        api_key_obj = result.scalar_one_or_none()

        if not api_key_obj:
            return None

        # Check expiration
        if api_key_obj.expires_at and api_key_obj.expires_at < datetime.now(timezone.utc):
            return None

        # Update last used timestamp
        api_key_obj.last_used_at = datetime.now(timezone.utc)
        await db.commit()

        return api_key_obj

    @staticmethod
    def require_permission(permission: str):
        """
        Dependency to check API key permissions

        Usage:
            @router.post("/admin/users")
            async def create_user(
                api_key: APIKey = Depends(APIManagement.require_permission("admin:write"))
            ):
                ...
        """

        async def check_permission(
                api_key: Optional[APIKey] = Depends(APIManagement.get_api_key)
        ):
            if not api_key:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API key required for this operation"
                )

            # Check if key has required permission or wildcard
            if permission not in api_key.permissions and "*" not in api_key.permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required permission: {permission}"
                )

            return api_key

        return check_permission

    @staticmethod
    async def create_api_key(
            db: AsyncSession,
            name: str,
            permissions: List[str] = None,
            rate_limit_override: Optional[int] = None,
            expires_in_days: Optional[int] = None
    ) -> tuple[str, APIKey]:
        """
        Create a new API key

        Returns:
            Tuple of (raw_key, api_key_object)
        """
        # Generate secure random key
        raw_key = f"chk_{secrets.token_urlsafe(32)}"

        # Hash the key for storage
        from app.auth.security import Hasher
        key_hash = Hasher.get_password_hash(raw_key)

        # Calculate expiration
        expires_at = None
        if expires_in_days:
            from datetime import timedelta
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        # Create API key object
        api_key = APIKey(
            name=name,
            key_hash=key_hash,
            permissions=permissions or [],
            rate_limit_override=rate_limit_override,
            expires_at=expires_at
        )

        db.add(api_key)
        await db.commit()
        await db.refresh(api_key)

        return raw_key, api_key


# Enhanced rate limiting with API key support
class EnhancedRateLimiter:
    """
    Rate limiter that considers API keys for custom limits
    """

    @staticmethod
    def limit_with_api_key(default_limit: str):
        """
        Rate limiting that checks for API key overrides
        """

        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                request = kwargs.get('request')
                db = kwargs.get('db')

                # Check for API key
                api_key_value = request.headers.get("X-API-Key") if request else None
                custom_limit = None

                if api_key_value and db:
                    api_key = await APIManagement.get_api_key(
                        api_key=api_key_value,
                        db=db
                    )
                    if api_key and api_key.rate_limit_override:
                        custom_limit = f"{api_key.rate_limit_override}/hour"

                # Apply appropriate limit
                limit_to_use = custom_limit or default_limit

                @rate_limiter.limit(limit_to_use)
                async def limited_func(*args, **kwargs):
                    return await func(*args, **kwargs)

                return await limited_func(*args, **kwargs)

            return wrapper

        return decorator
