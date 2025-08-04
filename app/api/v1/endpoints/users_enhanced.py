# app/api/v1/endpoints/users_enhanced.py
"""
Enhanced users endpoint demonstrating all base features working automatically
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, and_, select
from datetime import datetime, timedelta
from typing import Optional, List

from app.db.database import get_db
from app.db.crud.user import get_user_by_id, get_active_user_count
from app.api.v1.schemas.users import UserResponse
from app.auth.dependencies import get_current_user
from app.db.models import User, RefreshToken, BlacklistedToken
from app.core import tracing
from app.core.api_management import APIManagement
from app.core.pagination import (
    PaginatedResponse,
    PaginationParams,
    get_pagination,
    AutoPaginator
)

router = APIRouter()


@router.get("/me", response_model=UserResponse)
@APIManagement.rate_limit(operation_type="read")  # Uses base rate limiting
async def read_current_user(
        request: Request,
        current_user: User = Depends(get_current_user)
):
    """
    Get current user profile.

    Base features working automatically:
    - ✅ Audit Trail: This request is logged automatically
    - ✅ Rate Limiting: 100/min for read operations
    - ✅ Compression: Response will be compressed if > 1KB
    - ✅ Tracing: Full request correlation
    """
    return current_user


@router.get("/", response_model=PaginatedResponse[UserResponse])
@APIManagement.rate_limit(operation_type="read")
async def list_users(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        pagination: PaginationParams = Depends(get_pagination),
        is_active: Optional[bool] = None
):
    """
    List all users with automatic pagination.

    Base features:
    - ✅ Automatic Pagination: Use ?page=1&size=20&sort_by=email&search=john
    - ✅ Audit Trail: Access is logged with user details
    - ✅ Compression: Large responses are automatically compressed
    - ✅ Rate Limiting: Protected with read operation limits

    Query parameters:
    - page: Page number (default: 1)
    - size: Items per page (default: 20, max: 100)
    - sort_by: Field to sort by (e.g., email, created_at)
    - sort_order: asc or desc (default: asc)
    - search: Search term (searches in email)
    - is_active: Filter by active status
    """
    # Build filters
    filters = {}
    if is_active is not None:
        filters['is_active'] = is_active

    # Use automatic pagination with search
    result = await AutoPaginator.paginate(
        db=db,
        model=User,
        params=pagination,
        response_schema=UserResponse,
        filters=filters,
        search_fields=['email'],  # Search in email field
        request=request  # For building links
    )

    tracing.info(
        f"Listed users",
        total=result.total,
        page=result.page,
        user=current_user.email
    )

    return result


@router.get("/{user_id}", response_model=UserResponse)
@APIManagement.rate_limit(operation_type="read")
async def get_user_by_id_endpoint(
        request: Request,
        user_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Get user by ID.

    All base features work automatically without any special code!
    """
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user


@router.get("/admin/metrics", response_model=dict)
@APIManagement.rate_limit(operation_type="admin")  # More restrictive rate limit
async def get_app_metrics(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        api_key=Depends(APIManagement.get_api_key)  # Optional API key
):
    """
    Get application metrics.

    Can be accessed with either:
    - Bearer token (JWT)
    - API Key header (X-API-Key)

    Base features:
    - ✅ API Management: Supports both JWT and API key auth
    - ✅ Rate Limiting: Admin rate limit (20/min)
    - ✅ Audit Trail: Admin access is logged
    - ✅ Compression: Metrics data is compressed
    """
    try:
        # If API key is used, it might have custom rate limit
        auth_method = "api_key" if api_key else "jwt"

        total_users = await db.scalar(func.count(User.id))
        active_users = await db.scalar(
            func.count(User.id).where(User.is_active == True)
        )

        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_users = await db.scalar(
            func.count(User.id).where(User.created_at >= yesterday)
        )

        active_tokens = await db.scalar(
            func.count(RefreshToken.id).where(
                and_(
                    RefreshToken.revoked_at.is_(None),
                    RefreshToken.expires_at > datetime.utcnow()
                )
            )
        )

        blacklisted_tokens = await db.scalar(func.count(BlacklistedToken.id))

        metrics = {
            "total_users": total_users or 0,
            "active_users": active_users or 0,
            "recent_registrations_24h": recent_users or 0,
            "active_refresh_tokens": active_tokens or 0,
            "blacklisted_tokens": blacklisted_tokens or 0,
            "auth_method": auth_method,
            "timestamp": datetime.utcnow().isoformat()
        }

        tracing.info(
            f"Metrics accessed",
            user=current_user.email if not api_key else "api_key",
            auth_method=auth_method
        )

        return metrics

    except Exception as e:
        tracing.error(f"Metrics fetch failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving metrics"
        )


@router.post("/batch-create", response_model=dict)
@APIManagement.rate_limit(operation_type="write")  # Write operation rate limit
async def batch_create_users(
        request: Request,
        users_data: List[dict],
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        api_key=Depends(APIManagement.require_permission("admin:write"))  # Requires permission
):
    """
    Batch create users (admin only).

    Demonstrates:
    - ✅ API Permission: Requires 'admin:write' permission in API key
    - ✅ Rate Limiting: Write operation limits (30/min)
    - ✅ Audit Trail: Batch operation is logged
    - ✅ Compression: Response compressed if large

    This endpoint requires an API key with 'admin:write' permission.
    """
    created_count = 0
    errors = []

    for user_data in users_data[:100]:  # Limit batch size
        try:
            # Create user logic here
            created_count += 1
        except Exception as e:
            errors.append({"email": user_data.get("email"), "error": str(e)})

    return {
        "created": created_count,
        "errors": errors,
        "total_requested": len(users_data)
    }


# Example of how all base features work together
"""
When a request comes to any endpoint:

1. **Compression Middleware** - Checks if response should be compressed
2. **Monitoring Middleware** - Records Prometheus metrics
3. **Audit Trail Middleware** - Logs the API access automatically
4. **Rate Limiting** - Applies appropriate limits based on operation type
5. **Your endpoint logic** - Executes with pagination if needed
6. **Response** - Compressed if > 1KB, with proper headers

No additional code needed in your endpoints for these features!
"""