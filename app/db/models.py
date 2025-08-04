import datetime
import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.db.database import Base

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

    # Enhanced indexes for better performance
    __table_args__ = (
        Index('idx_user_email_active', 'email', 'is_active'),
        Index('idx_user_created_at', 'created_at'),
        Index('idx_user_active', 'is_active'),
    )

    def __repr__(self):
        return f"<User email={self.email}>"

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    issued_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="refresh_tokens")

    # Enhanced indexes for better query performance
    __table_args__ = (
        Index('idx_refresh_token_user_active', 'user_id', 'revoked_at'),
        Index('idx_refresh_token_expires', 'expires_at'),
        Index('idx_refresh_token_hash', 'token_hash'),
        Index('idx_refresh_token_cleanup', 'expires_at', 'revoked_at'),
    )

    def __repr__(self):
        return f"<RefreshToken user_id={self.user_id} expires_at={self.expires_at}>"

class BlacklistedToken(Base):
    __tablename__ = "blacklisted_tokens"

    id = Column(Integer, primary_key=True, index=True)
    jti = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    blacklisted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Enhanced indexes for cleanup and lookup performance
    __table_args__ = (
        Index('idx_blacklisted_jti_expires', 'jti', 'expires_at'),
        Index('idx_blacklisted_expires', 'expires_at'),
        Index('idx_blacklisted_cleanup', 'expires_at', 'blacklisted_at'),
    )

    def __repr__(self):
        return f"<BlacklistedToken jti={self.jti}>"
