# app/auth/security.py
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from loguru import logger

from app.core.config import settings

import uuid

# Password hashing context (bcrypt is recommended)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Hasher:
    """
    Utility class for password hashing and verification for Chawk's users,
    and for hashing refresh tokens.
    """

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verifies a plain password against a hashed password.
        """
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        """
        Hashes a plain password.
        """
        return pwd_context.hash(password)

    @staticmethod
    def hash_refresh_token(token: str) -> str:
        """
        Hashes a refresh token before storing it in the database.
        Using bcrypt for refresh token hashing as well for consistency and security.
        """
        return pwd_context.hash(token)

    @staticmethod
    def verify_refresh_token(plain_token: str, hashed_token: str) -> bool:
        """
        Verifies a plain refresh token against its hashed version.
        """
        return pwd_context.verify(plain_token, hashed_token)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Creates a new JWT access token for Chawk.
    Includes 'jti' (JWT ID) for blacklisting.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    # Generate a unique JWT ID (JTI) for blacklisting
    jti = str(uuid.uuid4())
    to_encode.update({"exp": expire, "jti": jti, "type": "access"})  # Add jti and type

    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY.get_secret_value(), algorithm=settings.ALGORITHM
    )
    return encoded_jwt


# create_refresh_token (ensure it also has a "type": "refresh" and optionally a jti if you track refresh token blacklisting by JTI, but token_hash is better for revoking sessions)
def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Creates a new JWT refresh token for Chawk.
    Refresh tokens have a longer expiry time.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    # It's good practice to add a type to distinguish between access and refresh tokens
    to_encode.update({"exp": expire, "type": "refresh"})

    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY.get_secret_value(), algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def decode_token(token: str) -> dict:
    """
    Decodes a JWT token and returns its payload.
    Raises JWTError if the token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY.get_secret_value(), algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError as e:
        logger.warning(f"JWT decoding error: {e}")
        raise
