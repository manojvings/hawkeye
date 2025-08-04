# app/db/models/cortex.py
"""Cortex integration models for analyzers, responders, and jobs"""
from sqlalchemy import Column, Integer, String, Text, JSON, ForeignKey, Index, Enum, Boolean, DateTime, Float
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.models.base import Base, TimestampMixin, UUIDMixin
from app.db.models.enums import JobStatus, WorkerType


class CortexInstance(Base, UUIDMixin, TimestampMixin):
    """Cortex instance configuration"""
    __tablename__ = "cortex_instances"

    name = Column(String(255), nullable=False, index=True)
    url = Column(String(500), nullable=False)
    api_key = Column(String(255), nullable=False)  # Encrypted
    enabled = Column(Boolean, default=True, nullable=False)
    version = Column(String(50), nullable=True)
    
    # Organization filtering
    included_organizations = Column(JSON, default=list, nullable=False)  # ['*'] means all
    excluded_organizations = Column(JSON, default=list, nullable=False)
    
    # Connection settings
    verify_ssl = Column(Boolean, default=True, nullable=False)
    timeout = Column(Integer, default=60, nullable=False)  # seconds
    max_concurrent_jobs = Column(Integer, default=10, nullable=False)
    
    # Relationships
    analyzers = relationship("CortexAnalyzer", back_populates="cortex_instance", cascade="all, delete-orphan")
    responders = relationship("CortexResponder", back_populates="cortex_instance", cascade="all, delete-orphan")
    jobs = relationship("CortexJob", back_populates="cortex_instance")

    __table_args__ = (
        Index('idx_cortex_name_enabled', 'name', 'enabled'),
        Index('idx_cortex_uuid', 'uuid'),
    )

    def __repr__(self):
        return f"<CortexInstance name={self.name} url={self.url}>"


class CortexAnalyzer(Base, UUIDMixin, TimestampMixin):
    """Cortex analyzer definition"""
    __tablename__ = "cortex_analyzers"

    name = Column(String(255), nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    version = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    
    # Analyzer capabilities
    data_types = Column(JSON, nullable=False)  # ['ip', 'domain', 'hash', etc.]
    max_tlp = Column(Integer, default=3, nullable=False)  # 0=RED, 1=AMBER, 2=GREEN, 3=WHITE
    max_pap = Column(Integer, default=3, nullable=False)
    
    # Configuration
    configuration = Column(JSON, default=dict, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    rate_limit = Column(Integer, nullable=True)  # requests per minute
    
    # Status
    last_sync = Column(DateTime(timezone=True), nullable=True)
    is_available = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    cortex_instance_id = Column(Integer, ForeignKey("cortex_instances.id", ondelete="CASCADE"), nullable=False)
    cortex_instance = relationship("CortexInstance", back_populates="analyzers")
    jobs = relationship("CortexJob", back_populates="analyzer")

    __table_args__ = (
        Index('idx_analyzer_cortex_name', 'cortex_instance_id', 'name'),
        Index('idx_analyzer_enabled', 'enabled'),
        Index('idx_analyzer_data_types', 'data_types'),
    )

    def __repr__(self):
        return f"<CortexAnalyzer name={self.name} version={self.version}>"


class CortexResponder(Base, UUIDMixin, TimestampMixin):
    """Cortex responder definition"""
    __tablename__ = "cortex_responders"

    name = Column(String(255), nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    version = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    
    # Responder capabilities
    data_types = Column(JSON, nullable=False)  # ['ip', 'domain', 'hash', etc.]
    max_tlp = Column(Integer, default=3, nullable=False)
    max_pap = Column(Integer, default=3, nullable=False)
    
    # Configuration
    configuration = Column(JSON, default=dict, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    
    # Status
    last_sync = Column(DateTime(timezone=True), nullable=True)
    is_available = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    cortex_instance_id = Column(Integer, ForeignKey("cortex_instances.id", ondelete="CASCADE"), nullable=False)
    cortex_instance = relationship("CortexInstance", back_populates="responders")
    jobs = relationship("CortexJob", back_populates="responder")

    __table_args__ = (
        Index('idx_responder_cortex_name', 'cortex_instance_id', 'name'),
        Index('idx_responder_enabled', 'enabled'),
        Index('idx_responder_data_types', 'data_types'),
    )

    def __repr__(self):
        return f"<CortexResponder name={self.name} version={self.version}>"


class CortexJob(Base, UUIDMixin, TimestampMixin):
    """Cortex job execution tracking"""
    __tablename__ = "cortex_jobs"

    # Job identification
    cortex_job_id = Column(String(255), nullable=False, index=True)  # ID from Cortex
    worker_type = Column(Enum(WorkerType), nullable=False, index=True)
    
    # Job details
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.WAITING, index=True)
    message = Column(Text, nullable=True)
    progress = Column(Integer, default=0, nullable=False)  # 0-100
    
    # Execution timing
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration = Column(Float, nullable=True)  # seconds
    
    # Job data
    parameters = Column(JSON, default=dict, nullable=False)
    report = Column(JSON, nullable=True)  # Analysis/response report
    artifacts = Column(JSON, default=list, nullable=False)  # Generated artifacts
    
    # Relationships
    cortex_instance_id = Column(Integer, ForeignKey("cortex_instances.id", ondelete="CASCADE"), nullable=False)
    cortex_instance = relationship("CortexInstance", back_populates="jobs")
    
    analyzer_id = Column(Integer, ForeignKey("cortex_analyzers.id", ondelete="SET NULL"), nullable=True)
    analyzer = relationship("CortexAnalyzer", back_populates="jobs")
    
    responder_id = Column(Integer, ForeignKey("cortex_responders.id", ondelete="SET NULL"), nullable=True)
    responder = relationship("CortexResponder", back_populates="jobs")
    
    # Source data (what was analyzed/responded to)
    observable_id = Column(Integer, ForeignKey("observables.id", ondelete="CASCADE"), nullable=True)
    observable = relationship("Observable", backref="cortex_jobs")
    
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=True)
    case = relationship("Case", backref="cortex_jobs")
    
    # User who triggered the job
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_by = relationship("User", backref="cortex_jobs")

    __table_args__ = (
        Index('idx_cortex_job_status', 'status'),
        Index('idx_cortex_job_cortex_id', 'cortex_job_id'),
        Index('idx_cortex_job_observable', 'observable_id'),
        Index('idx_cortex_job_case', 'case_id'),
        Index('idx_cortex_job_created', 'created_at'),
        Index('idx_cortex_job_user', 'created_by_id'),
    )

    def __repr__(self):
        return f"<CortexJob id={self.cortex_job_id} status={self.status} type={self.worker_type}>"