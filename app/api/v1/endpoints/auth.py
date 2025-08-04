# app/api/v1/endpoints/auth.py - Fully trace-integrated with OpenTelemetry
from fastapi import APIRouter, Depends, HTTPException, status, Form, Request
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address
from datetime import datetime, timezone
from jose import JWTError

from app.db.database import get_db
from app.auth.security import Hasher, create_access_token, create_refresh_token, decode_token
from app.db.crud.user import get_user_by_email, create_user_db
from app.db.crud.token import create_refresh_token_db, get_refresh_token_by_hash, revoke_refresh_token_db, add_to_blacklist
from app.api.v1.schemas.auth import Token, UserCreate, UserLogin
from app.db.models import User
from app.core.config import settings
from app.core import tracing

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


async def issue_tokens_and_save_refresh(db: AsyncSession, user: User) -> dict:
    access_token_data = {"sub": user.email, "user_id": user.id, "type": "access"}
    refresh_token_data = {"sub": user.email, "user_id": user.id, "type": "refresh", "jti": str(user.id)}

    access_token = create_access_token(data=access_token_data)
    refresh_token = create_refresh_token(data=refresh_token_data)

    refresh_token_payload = decode_token(refresh_token)
    refresh_expires_at = datetime.fromtimestamp(refresh_token_payload["exp"], tz=timezone.utc)

    try:
        await create_refresh_token_db(db, user.id, refresh_token, refresh_expires_at)
        tracing.info("Refresh token saved", email=user.email, user_id=user.id)
    except Exception as e:
        tracing.error("Failed to save refresh token", email=user.email, user_id=user.id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save refresh token.")

    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register_user(request: Request, user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    ip = get_remote_address(request)
    tracing.info("Registration attempt", email=user_in.email, ip=ip)

    existing_user = await get_user_by_email(db, user_in.email)
    if existing_user:
        tracing.warning("Registration failed - user exists", email=user_in.email, ip=ip)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User with this email already exists.")

    hashed_password = Hasher.get_password_hash(user_in.password)
    user_data = {"email": user_in.email, "hashed_password": hashed_password}

    try:
        user = await create_user_db(db, user_data)
        tracing.info("User registered successfully", email=user.email, user_id=user.id, ip=ip)
        return await issue_tokens_and_save_refresh(db, user)
    except Exception as e:
        tracing.error("Failed to create user", email=user_in.email, ip=ip, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create user.")


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    ip = get_remote_address(request)
    tracing.info("Login attempt", username=form_data.username, ip=ip)

    user = await get_user_by_email(db, form_data.username)
    if not user or not Hasher.verify_password(form_data.password, user.hashed_password):
        tracing.warning("Login failed - invalid credentials", username=form_data.username, ip=ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    if not user.is_active:
        tracing.warning("Login failed - account inactive", username=form_data.username, ip=ip)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive.")

    tracing.info("Login successful", email=user.email, user_id=user.id, ip=ip)
    return await issue_tokens_and_save_refresh(db, user)


@router.post("/login-json", response_model=Token)
@limiter.limit("5/minute")
async def login_via_json(request: Request, user_login: UserLogin, db: AsyncSession = Depends(get_db)):
    ip = get_remote_address(request)
    tracing.info("JSON login attempt", username=user_login.username, ip=ip)

    user = await get_user_by_email(db, user_login.username)
    if not user or not Hasher.verify_password(user_login.password, user.hashed_password):
        tracing.warning("JSON login failed - invalid credentials", username=user_login.username, ip=ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    if not user.is_active:
        tracing.warning("JSON login failed - account inactive", username=user_login.username, ip=ip)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive.")

    tracing.info("JSON login successful", email=user.email, user_id=user.id, ip=ip)
    return await issue_tokens_and_save_refresh(db, user)


@router.post("/refresh-token", response_model=Token)
@limiter.limit("10/minute")
async def refresh_access_token(request: Request, refresh_token: str = Form(...), db: AsyncSession = Depends(get_db)):
    ip = get_remote_address(request)
    tracing.info("Token refresh attempt", ip=ip)

    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    try:
        payload = decode_token(refresh_token)
        user_id = payload.get("user_id")
        token_type = payload.get("type")
        jti = payload.get("jti")

        if user_id is None or token_type != "refresh" or jti is None:
            raise credentials_exception
    except Exception as e:
        tracing.warning("Invalid refresh token", ip=ip, error=str(e))
        raise credentials_exception

    hashed_token = Hasher.hash_refresh_token(refresh_token)
    token_record = await get_refresh_token_by_hash(db, hashed_token)

    if not token_record:
        tracing.warning("Refresh token not found", user_id=user_id, ip=ip)
        raise credentials_exception

    user = await get_user_by_email(db, payload.get("sub"))
    if not user or not user.is_active:
        tracing.warning("Refresh token - inactive user", username=payload.get("sub"), ip=ip)
        raise credentials_exception

    try:
        await revoke_refresh_token_db(db, token_record)
        tracing.info("Token refresh successful", email=user.email, user_id=user.id, ip=ip)
        return await issue_tokens_and_save_refresh(db, user)
    except Exception as e:
        tracing.error("Failed to refresh token", email=user.email, ip=ip, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to refresh token.")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def logout(request: Request, access_token: str = Depends(OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")), db: AsyncSession = Depends(get_db)):
    ip = get_remote_address(request)
    tracing.info("Logout attempt", ip=ip)

    try:
        payload = decode_token(access_token)
        jti = payload.get("jti")
        exp = payload.get("exp")
        email = payload.get("sub")

        if jti is None or exp is None:
            tracing.warning("Invalid token for logout", ip=ip)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token for logout.")

        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
        await add_to_blacklist(db, jti, expires_at)

        tracing.info("Logout successful", email=email, ip=ip)
    except Exception as e:
        tracing.error("Logout failed", ip=ip, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Logout failed.")
