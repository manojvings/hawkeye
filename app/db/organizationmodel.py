# Add these to your existing app/db/models.py file

import enum
import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, ForeignKey, Index, Enum, JSON, Text, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.database import Base


# ============= ENUMS =============

class Severity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TLP(str, enum.Enum):
    WHITE = "white"
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class CaseStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AlertStatus(str, enum.Enum):
    NEW = "new"
    UPDATED = "updated"
    IGNORED = "ignored"
    IMPORTED = "imported"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    ORG_ADMIN = "org_admin"
    ANALYST = "analyst"
    READ_ONLY = "read_only"


class ObservableType(str, enum.Enum):
    DOMAIN = "domain"
    FILE = "file"
    FILENAME = "filename"
    FQDN = "fqdn"
    HASH = "hash"
    IP = "ip"
    MAIL = "mail"
    MAIL_SUBJECT = "mail_subject"
    OTHER = "other"
    REGEXP = "regexp"
    REGISTRY = "registry"
    URI_PATH = "uri_path"
    URL = "url"
    USER_AGENT = "user-agent"


# ============= SIRP MODELS =============

class Organization(Base):
    __tablename__ = "organizations"

    # Hybrid ID system
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(UUID(as_uuid=True), unique=True, default=uuid.uuid4, index=True, nullable=False)

    # Organization fields
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    settings = Column(JSON, default=dict, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now(), nullable=False)

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


class UserOrganization(Base):
    __tablename__ = "user_organizations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.ANALYST)

    # Timestamps
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="organizations")
    organization = relationship("Organization", back_populates="members")

    __table_args__ = (
        Index('idx_user_org_composite', 'user_id', 'organization_id', unique=True),
        Index('idx_user_org_role', 'organization_id', 'role'),
    )

    def __repr__(self):
        return f"<UserOrganization user_id={self.user_id} org_id={self.organization_id} role={self.role}>"


# Update User model to add organizations relationship
# Add this line to your existing User model:
# organizations = relationship("UserOrganization", back_populates="user", cascade="all, delete-orphan")


class Case(Base):
    __tablename__ = "cases"

    # Hybrid ID system
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(UUID(as_uuid=True), unique=True, default=uuid.uuid4, index=True, nullable=False)

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

    # Foreign keys
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    assignee_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now(), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)

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
    )

    def __repr__(self):
        return f"<Case case_number={self.case_number} title={self.title}>"


class Task(Base):
    __tablename__ = "tasks"

    # Hybrid ID system
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(UUID(as_uuid=True), unique=True, default=uuid.uuid4, index=True, nullable=False)

    # Task fields
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.PENDING, index=True)
    order_index = Column(Integer, nullable=False, default=0)
    due_date = Column(DateTime(timezone=True), nullable=True)

    # Foreign keys
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    assignee_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    case = relationship("Case", back_populates="tasks")
    assignee = relationship("User", foreign_keys=[assignee_id], backref="assigned_tasks")
    created_by = relationship("User", foreign_keys=[created_by_id], backref="created_tasks")

    __table_args__ = (
        Index('idx_task_case_order', 'case_id', 'order_index'),
        Index('idx_task_assignee_status', 'assignee_id', 'status'),
    )

    def __repr__(self):
        return f"<Task title={self.title} status={self.status}>"


class Observable(Base):
    __tablename__ = "observables"

    # Hybrid ID system
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(UUID(as_uuid=True), unique=True, default=uuid.uuid4, index=True, nullable=False)

    # Observable fields
    data_type = Column(Enum(ObservableType), nullable=False, index=True)
    data = Column(String(1000), nullable=False, index=True)  # The actual observable value
    tlp = Column(Enum(TLP), nullable=False, default=TLP.AMBER)
    is_ioc = Column(Boolean, default=False, nullable=False, index=True)
    tags = Column(JSON, default=list, nullable=False)
    source = Column(String(255), nullable=True)
    message = Column(Text, nullable=True)
    sighted_count = Column(Integer, default=0, nullable=False)

    # Foreign keys
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now(), nullable=False)

    # Relationships
    case = relationship("Case", back_populates="observables")
    created_by = relationship("User", backref="created_observables")

    __table_args__ = (
        Index('idx_observable_type_ioc', 'data_type', 'is_ioc'),
        Index('idx_observable_data', 'data'),
        Index('idx_observable_case', 'case_id'),
    )

    def __repr__(self):
        return f"<Observable type={self.data_type} data={self.data[:50]}>"


class Alert(Base):
    __tablename__ = "alerts"

    # Hybrid ID system
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(UUID(as_uuid=True), unique=True, default=uuid.uuid4, index=True, nullable=False)

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

    # Foreign keys
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, unique=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now(), nullable=False)
    imported_at = Column(DateTime(timezone=True), nullable=True)  # When converted to case

    # Relationships
    organization = relationship("Organization", back_populates="alerts")
    case = relationship("Case", back_populates="alert", uselist=False)
    created_by = relationship("User", backref="created_alerts")

    __table_args__ = (
        Index('idx_alert_org_status', 'organization_id', 'status'),
        Index('idx_alert_source', 'source'),
        Index('idx_alert_created', 'created_at'),
        Index('idx_alert_source_ref', 'source', 'source_ref', unique=True),
    )

    def __repr__(self):
        return f"<Alert source={self.source} title={self.title}>"