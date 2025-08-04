# app/api/v1/schemas/users.py
from pydantic import BaseModel, EmailStr
from datetime import datetime

class UserBase(BaseModel):
    """
    Base schema for Chawk user, containing common attributes.
    """
    email: EmailStr
    is_active: bool = True

class UserResponse(UserBase):
    """
    Schema for a Chawk user response, including ID and timestamps.
    """
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True # Allows Pydantic to read from ORM models