import datetime
import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.db.database import Base
from sqlalchemy.dialects.postgresql import UUID


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now(), nullable=False)
    # Relationship to RefreshTokens
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    organizations = relationship("UserOrganization", back_populates="user", cascade="all, delete-orphan")

    # Enhanced indexes for better performance
    __table_args__ = (
        Index('idx_user_email_active', 'email', 'is_active'),
        Index('idx_user_created_at', 'created_at'),
        Index('idx_user_active', 'is_active'),
    )

    def __repr__(self):
        return f"<User email={self.email}>"
