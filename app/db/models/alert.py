# app/db/models/alert.py
"""Alert management model"""
from sqlalchemy import Column, Integer, String, Text, JSON, ForeignKey, Index, Enum, DateTime
from sqlalchemy.orm import relationship

from app.db.models.base import Base, TimestampMixin, UUIDMixin
from app.db.models.enums import Severity, TLP, AlertStatus


class Alert(Base, UUIDMixin, TimestampMixin):
    """Alert model for incoming security alerts"""
    __tablename__ = "alerts"

    # Alert fields
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    source = Column(String(255), nullable=False, index=True)
    source_ref = Column(String(255), nullable=False)  # Reference in source system
    severity = Column(Enum(Severity), nullable=False, default=Severity.MEDIUM)
    tlp = Column(Enum(TLP), nullable=False, default=TLP.AMBER)
    status = Column(Enum(AlertStatus), nullable=False, default=AlertStatus.NEW, index=True)
    raw_data = Column(JSON, default=dict, nullable=False)
    observables = Column(JSON, default=list, nullable=False)  # Embedded observables
    imported_at = Column(DateTime(timezone=True), nullable=True)  # When converted to case

    # Foreign keys
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, unique=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    organization = relationship("Organization", back_populates="alerts")
    case = relationship("Case", back_populates="alert", uselist=False)
    created_by = relationship("User", backref="created_alerts")

    __table_args__ = (
        Index('idx_alert_org_status', 'organization_id', 'status'),
        Index('idx_alert_source', 'source'),
        Index('idx_alert_created', 'created_at'),
        Index('idx_alert_source_ref', 'source', 'source_ref', unique=True),
        Index('idx_alert_uuid', 'uuid'),
    )

    def __repr__(self):
        return f"<Alert source={self.source} title={self.title}>"