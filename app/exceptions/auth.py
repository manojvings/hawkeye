# app/exceptions/auth.py
from fastapi import HTTPException, status

class AuthenticationError(HTTPException):
    """Base authentication error"""
    def __init__(self, detail: str = "Authentication failed"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"}
        )

class InvalidCredentialsError(AuthenticationError):
    """Invalid username/password"""
    def __init__(self):
        super().__init__(detail="Invalid username or password")

class TokenExpiredError(AuthenticationError):
    """Token has expired"""
    def __init__(self):
        super().__init__(detail="Token has expired")

class TokenBlacklistedError(AuthenticationError):
    """Token has been blacklisted"""
    def __init__(self):
        super().__init__(detail="Token has been revoked")

class InactiveUserError(HTTPException):
    """User account is inactive"""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )

class UserAlreadyExistsError(HTTPException):
    """User already exists"""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists"
        )

class WeakPasswordError(HTTPException):
    """Password doesn't meet complexity requirements"""
    def __init__(self, detail: str = "Password doesn't meet security requirements"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )