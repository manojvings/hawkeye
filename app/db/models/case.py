# app/db/models/case.py
"""Case management model"""
from sqlalchemy import Column, Integer, String, Text, JSON, ForeignKey, Index, Enum, DateTime
from sqlalchemy.orm import relationship

from app.db.models.base import Base, TimestampMixin, UUIDMixin
from app.db.models.enums import Severity, TLP, CaseStatus


class Case(Base, UUIDMixin, TimestampMixin):
    """Security incident case model"""
    __tablename__ = "cases"

    # Case fields
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    case_number = Column(String(50), unique=True, nullable=False, index=True)  # Auto-generated
    severity = Column(Enum(Severity), nullable=False, default=Severity.MEDIUM)
    tlp = Column(Enum(TLP), nullable=False, default=TLP.AMBER)
    status = Column(Enum(CaseStatus), nullable=False, default=CaseStatus.OPEN, index=True)
    tags = Column(JSON, default=list, nullable=False)
    custom_fields = Column(JSON, default=dict, nullable=False)
    due_date = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    # Foreign keys
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    assignee_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="cases")
    assignee = relationship("User", foreign_keys=[assignee_id], backref="assigned_cases")
    created_by = relationship("User", foreign_keys=[created_by_id], backref="created_cases")
    tasks = relationship("Task", back_populates="case", cascade="all, delete-orphan")
    observables = relationship("Observable", back_populates="case", cascade="all, delete-orphan")
    alert = relationship("Alert", back_populates="case", uselist=False)

    __table_args__ = (
        Index('idx_case_org_status', 'organization_id', 'status'),
        Index('idx_case_assignee', 'assignee_id'),
        Index('idx_case_severity', 'severity'),
        Index('idx_case_created', 'created_at'),
        Index('idx_case_uuid', 'uuid'),
    )

    def __repr__(self):
        return f"<Case case_number={self.case_number} title={self.title}>"