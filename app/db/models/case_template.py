# app/db/models/case_template.py
"""Case Template model for template-based case creation"""
from sqlalchemy import Column, Integer, String, Text, Boolean, JSON, ForeignKey, Index, Enum
from sqlalchemy.orm import relationship

from app.db.models.base import Base, TimestampMixin, UUIDMixin
from app.db.models.enums import Severity, TLP


class CaseTemplate(Base, UUIDMixin, TimestampMixin):
    """Case template model for creating standardized cases"""
    __tablename__ = "case_templates"

    # Template identification
    name = Column(String(255), nullable=False, index=True)  # Unique identifier
    display_name = Column(String(255), nullable=False)  # Human-readable name
    title_prefix = Column(String(100), nullable=True)  # Prefix for case titles
    description = Column(Text, nullable=True)  # Template description
    
    # Default case settings
    severity = Column(Enum(Severity), nullable=True)  # Default severity
    tlp = Column(Enum(TLP), nullable=True, default=TLP.AMBER)  # Default TLP
    pap = Column(Enum(TLP), nullable=True, default=TLP.AMBER)  # Default PAP (uses TLP enum)
    flag = Column(Boolean, default=False, nullable=False)  # Default flag status
    tags = Column(JSON, default=list, nullable=False)  # Default tags
    custom_fields = Column(JSON, default=dict, nullable=False)  # Default custom fields
    summary = Column(Text, nullable=True)  # Default summary template
    
    # Template metadata
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    usage_count = Column(Integer, default=0, nullable=False)  # Track template usage
    
    # Foreign keys
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="case_templates")
    created_by = relationship("User", backref="created_case_templates")
    task_templates = relationship("TaskTemplate", back_populates="case_template", cascade="all, delete-orphan")
    cases = relationship("Case", back_populates="template", foreign_keys="Case.case_template_id")

    __table_args__ = (
        Index('idx_case_template_org_name', 'organization_id', 'name', unique=True),
        Index('idx_case_template_active', 'is_active'),
        Index('idx_case_template_usage', 'usage_count'),
        Index('idx_case_template_created', 'created_at'),
        Index('idx_case_template_uuid', 'uuid'),
    )

    def __repr__(self):
        return f"<CaseTemplate name={self.name} display_name={self.display_name}>"


class TaskTemplate(Base, UUIDMixin, TimestampMixin):
    """Task template model for predefined tasks in case templates"""
    __tablename__ = "task_templates"

    # Task template fields
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    group = Column(String(100), nullable=False, default="default")  # Task grouping
    order_index = Column(Integer, nullable=False, default=0)  # Order within template
    
    # Default task settings
    flag = Column(Boolean, default=False, nullable=False)
    assignee_role = Column(String(50), nullable=True)  # Role to assign task to (analyst, admin, etc.)
    due_days_offset = Column(Integer, nullable=True)  # Days from case creation for due date
    
    # Task dependencies (JSON array of task template UUIDs)
    depends_on = Column(JSON, default=list, nullable=False)  # Task dependencies
    
    # Foreign keys
    case_template_id = Column(Integer, ForeignKey("case_templates.id", ondelete="CASCADE"), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False)

    # Relationships
    case_template = relationship("CaseTemplate", back_populates="task_templates")
    created_by = relationship("User", backref="created_task_templates")

    __table_args__ = (
        Index('idx_task_template_case', 'case_template_id'),
        Index('idx_task_template_order', 'case_template_id', 'order_index'),
        Index('idx_task_template_group', 'group'),
        Index('idx_task_template_uuid', 'uuid'),
    )

    def __repr__(self):
        return f"<TaskTemplate title={self.title} order={self.order_index}>"