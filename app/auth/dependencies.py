# app/auth/dependencies.py - Clean OpenTelemetry-only dependencies
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError
from loguru import logger

from app.db.database import get_db
from app.auth.security import decode_token
from app.db.crud.user import get_user_by_id
from app.db.crud.token import is_jti_blacklisted
from app.api.v1.schemas.auth import TokenData
from app.db.models import User

# OAuth2PasswordBearer for token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
        db: AsyncSession = Depends(get_db),
        token: str = Depends(oauth2_scheme)
) -> User:
    """
    Get currently authenticated user with OpenTelemetry trace context
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Decode JWT token
        payload = decode_token(token)
        email: str = payload.get("sub")
        user_id: int = payload.get("user_id")
        jti: str = payload.get("jti")

        if not all([email, user_id, jti]):
            logger.warning("Invalid token payload - missing required fields")
            raise credentials_exception

        # Check if token is blacklisted
        if await is_jti_blacklisted(db, jti):
            logger.warning(f"Blacklisted token used | jti={jti}")
            raise credentials_exception

        token_data = TokenData(email=email, user_id=user_id)

    except JWTError as e:
        logger.warning(f"JWT decode error: {e}")
        raise credentials_exception

    # Get user from database
    user = await get_user_by_id(db, token_data.user_id)
    if not user:
        logger.warning(f"User not found | user_id={token_data.user_id}")
        raise credentials_exception

    if not user.is_active:
        logger.warning(f"Inactive user authentication attempt | email={user.email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )

    logger.debug(f"User authenticated successfully | email={user.email} | user_id={user.id}")
    return user