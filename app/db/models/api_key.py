# In app/db/models/api_key.py, update the model to add UUID:

from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.db.database import Base

class APIKey(Base):
    """API Key model for service-to-service authentication"""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(UUID(as_uuid=True), unique=True, default=uuid.uuid4, index=True, nullable=False)  # ADD THIS
    name = Column(String(255), nullable=False)
    key_hash = Column(String(255), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    permissions = Column(JSON, default=list)
    rate_limit_override = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default='CURRENT_TIMESTAMP')
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)