# app/db/models/organization.py
"""Organization and multi-tenancy models"""
from sqlalchemy import Column, Integer, String, Boolean, Text, JSON, ForeignKey, Index, Enum
from sqlalchemy.orm import relationship

from app.db.models.base import Base, TimestampMixin, UUIDMixin
from app.db.models.enums import UserRole


class Organization(Base, UUIDMixin, TimestampMixin):
    """Organization model for multi-tenancy"""
    __tablename__ = "organizations"

    # Organization fields
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    settings = Column(JSON, default=dict, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    members = relationship("UserOrganization", back_populates="organization", cascade="all, delete-orphan")
    cases = relationship("Case", back_populates="organization", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="organization", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_org_name_active', 'name', 'is_active'),
        Index('idx_org_uuid', 'uuid'),
    )

    def __repr__(self):
        return f"<Organization name={self.name}>"


class UserOrganization(Base, TimestampMixin):
    """Many-to-many relationship between users and organizations with roles"""
    __tablename__ = "user_organizations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.ANALYST)

    # Note: joined_at is handled by TimestampMixin's created_at

    # Relationships
    user = relationship("User", back_populates="organizations")
    organization = relationship("Organization", back_populates="members")

    __table_args__ = (
        Index('idx_user_org_composite', 'user_id', 'organization_id', unique=True),
        Index('idx_user_org_role', 'organization_id', 'role'),
    )

    def __repr__(self):
        return f"<UserOrganization user_id={self.user_id} org_id={self.organization_id} role={self.role}>"