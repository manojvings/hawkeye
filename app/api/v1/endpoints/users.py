# app/api/v1/endpoints/users.py - OpenTelemetry tracing enabled
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, and_
from datetime import datetime, timedelta
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.db.database import get_db
from app.db.crud.user import get_user_by_id
from app.api.v1.schemas.users import UserResponse
from app.auth.dependencies import get_current_user
from app.db.models import User, RefreshToken, BlacklistedToken
from app.core import tracing

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("/me", response_model=UserResponse)
@limiter.limit("30/minute")
async def read_current_user(request: Request, current_user: User = Depends(get_current_user)):
    ip = get_remote_address(request)
    tracing.info("User profile requested", user_email=current_user.email, ip=ip)
    return current_user


@router.get("/{user_id}", response_model=UserResponse)
@limiter.limit("20/minute")
async def get_user_by_id_endpoint(
        request: Request,
        user_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    ip = get_remote_address(request)
    tracing.info("User lookup initiated", user_id=user_id, requester=current_user.email, ip=ip)

    user = await get_user_by_id(db, user_id)
    if not user:
        tracing.warning("User not found", user_id=user_id, requester=current_user.email, ip=ip)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    return user


@router.get("/admin/metrics", response_model=dict)
@limiter.limit("10/minute")
async def get_app_metrics(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    ip = get_remote_address(request)
    tracing.info("Metrics requested", user=current_user.email, ip=ip)

    try:
        total_users = await db.scalar(func.count(User.id))
        active_users = await db.scalar(func.count(User.id).where(User.is_active == True))

        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_users = await db.scalar(func.count(User.id).where(User.created_at >= yesterday))

        active_tokens = await db.scalar(func.count(RefreshToken.id).where(
            and_(
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.utcnow()
            )
        ))

        blacklisted_tokens = await db.scalar(func.count(BlacklistedToken.id))

        return {
            "total_users": total_users or 0,
            "active_users": active_users or 0,
            "recent_registrations_24h": recent_users or 0,
            "active_refresh_tokens": active_tokens or 0,
            "blacklisted_tokens": blacklisted_tokens or 0,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        tracing.error("Metrics fetch failed", user=current_user.email, ip=ip, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving metrics"
        )
