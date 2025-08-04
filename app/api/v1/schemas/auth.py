# app/api/v1/schemas/auth.py
from pydantic import BaseModel, EmailStr, Field, model_validator
from typing import Optional
import re  # Add this import at the top of the file


class Token(BaseModel):
    """
    Schema for JWT tokens returned by Chawk's authentication endpoints.
    """
    access_token: str
    token_type: str = "bearer"  # Standard token type
    refresh_token: Optional[str] = None  # Optional for refresh flow


class TokenData(BaseModel):
    """
    Schema for data contained within a JWT token payload for Chawk.
    """
    email: Optional[EmailStr] = None
    user_id: Optional[int] = None  # To identify the user from the Chawk database


class UserCreate(BaseModel):
    email: EmailStr = Field(..., description="User's email address.")
    password: str = Field(
        ...,
        min_length=8,
        max_length=64,
        # Removed the problematic regex; validation will be done in custom validator
        description="Password must be at least 8 characters long, include uppercase, lowercase, numbers, and special characters."
    )
    password_confirm: str = Field(..., description="Confirm password must match the password field.")

    @model_validator(mode='after')
    def validate_password_complexity(self) -> 'UserCreate':
        # Check for password complexity after initial validation
        password = self.password
        if not re.search(r"[a-z]", password):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"[A-Z]", password):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"\d", password):
            raise ValueError("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
            raise ValueError("Password must contain at least one special character.")
        return self

    @model_validator(mode='after')
    def passwords_match(self) -> 'UserCreate':
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match.")
        return self


class UserLogin(BaseModel):
    """
    Schema for user login credentials for Chawk.
    """
    username: EmailStr = Field(..., description="User's email address for login.")
    password: str = Field(..., description="User's password for login.")
