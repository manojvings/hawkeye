# app/api/v1/schemas/organizations.py
from pydantic import BaseModel, Field, UUID4
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# Import the UserRole enum (or redefine it here)
class UserRole(str, Enum):
    ADMIN = "admin"
    ORG_ADMIN = "org_admin"
    ANALYST = "analyst"
    READ_ONLY = "read_only"


class OrganizationBase(BaseModel):
    """Base schema for organization"""
    name: str = Field(..., min_length=1, max_length=255, description="Organization name")
    description: Optional[str] = Field(None, description="Organization description")
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Organization-specific settings")


class OrganizationCreate(OrganizationBase):
    """Schema for creating organization"""
    pass


class OrganizationUpdate(BaseModel):
    """Schema for updating organization"""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Organization name")
    description: Optional[str] = Field(None, description="Organization description")
    settings: Optional[Dict[str, Any]] = Field(None, description="Organization-specific settings")
    is_active: Optional[bool] = Field(None, description="Whether organization is active")


class OrganizationResponse(OrganizationBase):
    """Schema for organization response with UUID"""
    id: UUID4 = Field(..., description="Organization UUID")
    is_active: bool = Field(..., description="Whether organization is active")
    created_at: datetime
    updated_at: datetime
    member_count: Optional[int] = Field(None, description="Number of members")
    case_count: Optional[int] = Field(None, description="Number of cases")

    @classmethod
    def from_model(cls, org, member_count: Optional[int] = None, case_count: Optional[int] = None):
        """Convert Organization model to API response using UUID"""
        return cls(
            id=org.uuid,  # Map internal uuid to API id field
            name=org.name,
            description=org.description,
            settings=org.settings,
            is_active=org.is_active,
            created_at=org.created_at,
            updated_at=org.updated_at,
            member_count=member_count,
            case_count=case_count
        )

    class Config:
        from_attributes = True


class UserOrganizationBase(BaseModel):
    """Base schema for user-organization relationship"""
    role: UserRole = Field(..., description="User's role in the organization")


class AddOrganizationMember(UserOrganizationBase):
    """Schema for adding member to organization"""
    user_email: str = Field(..., description="Email of user to add")


class UserOrganizationResponse(UserOrganizationBase):
    """Schema for user-organization response"""
    user_id: UUID4 = Field(..., description="User UUID")
    user_email: str = Field(..., description="User email")
    organization_id: UUID4 = Field(..., description="Organization UUID")
    organization_name: str = Field(..., description="Organization name")
    joined_at: datetime

    @classmethod
    def from_model(cls, user_org):
        """Convert UserOrganization model to API response"""
        return cls(
            user_id=user_org.user.uuid,
            user_email=user_org.user.email,
            organization_id=user_org.organization.uuid,
            organization_name=user_org.organization.name,
            role=user_org.role.value,
            joined_at=user_org.joined_at
        )

    class Config:
        from_attributes = True


class OrganizationWithRole(OrganizationResponse):
    """Organization response with user's role"""
    user_role: UserRole = Field(..., description="User's role in this organization")

    @classmethod
    def from_user_org(cls, user_org, member_count: Optional[int] = None, case_count: Optional[int] = None):
        """Create from UserOrganization relationship"""
        org_data = OrganizationResponse.from_model(
            user_org.organization,
            member_count=member_count,
            case_count=case_count
        )
        return cls(
            **org_data.dict(),
            user_role=user_org.role.value
        )