# app/db/models/webhook.py
"""Webhook models for event notifications"""
from sqlalchemy import Column, Integer, String, Text, JSON, ForeignKey, Index, Enum, Boolean, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.models.base import Base, TimestampMixin, UUIDMixin
from app.db.models.enums import WebhookEvent, WebhookStatus


class Webhook(Base, UUIDMixin, TimestampMixin):
    """Webhook configuration for event notifications"""
    __tablename__ = "webhooks"

    # Basic configuration
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    url = Column(String(500), nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    
    # Security
    secret = Column(String(255), nullable=True)  # For signature verification
    verify_ssl = Column(Boolean, default=True, nullable=False)
    
    # Events to listen for
    events = Column(JSON, nullable=False)  # List of WebhookEvent values
    
    # Filtering
    organization_filter = Column(JSON, default=list, nullable=False)  # Empty = all orgs
    case_filter = Column(JSON, default=dict, nullable=False)  # Status, severity, etc.
    
    # Configuration
    timeout = Column(Integer, default=30, nullable=False)  # seconds
    max_retries = Column(Integer, default=3, nullable=False)
    retry_backoff = Column(Integer, default=60, nullable=False)  # seconds
    
    # Headers to include
    custom_headers = Column(JSON, default=dict, nullable=False)
    
    # Statistics
    total_sent = Column(Integer, default=0, nullable=False)
    total_failed = Column(Integer, default=0, nullable=False)
    last_triggered = Column(DateTime(timezone=True), nullable=True)
    last_success = Column(DateTime(timezone=True), nullable=True)
    last_failure = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    organization = relationship("Organization", backref="webhooks")
    
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_by = relationship("User", backref="created_webhooks")
    
    deliveries = relationship("WebhookDelivery", back_populates="webhook", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_webhook_org_enabled', 'organization_id', 'enabled'),
        Index('idx_webhook_events', 'events'),
        Index('idx_webhook_last_triggered', 'last_triggered'),
    )

    def __repr__(self):
        return f"<Webhook name={self.name} url={self.url}>"


class WebhookDelivery(Base, UUIDMixin, TimestampMixin):
    """Individual webhook delivery attempt tracking"""
    __tablename__ = "webhook_deliveries"

    # Delivery details
    event_type = Column(Enum(WebhookEvent), nullable=False, index=True)
    status = Column(Enum(WebhookStatus), nullable=False, default=WebhookStatus.PENDING, index=True)
    
    # Request details
    request_url = Column(String(500), nullable=False)
    request_method = Column(String(10), default="POST", nullable=False)
    request_headers = Column(JSON, nullable=False)
    request_body = Column(Text, nullable=False)
    
    # Response details
    response_status_code = Column(Integer, nullable=True)
    response_headers = Column(JSON, nullable=True)
    response_body = Column(Text, nullable=True)
    response_time = Column(Integer, nullable=True)  # milliseconds
    
    # Error handling
    error_message = Column(Text, nullable=True)
    attempt_count = Column(Integer, default=1, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    
    # Event context
    event_data = Column(JSON, nullable=False)  # The event payload
    
    # Source information
    triggered_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    triggered_by = relationship("User", backref="webhook_deliveries")
    
    # Related objects
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=True)
    case = relationship("Case", backref="webhook_deliveries")
    
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    task = relationship("Task", backref="webhook_deliveries")
    
    observable_id = Column(Integer, ForeignKey("observables.id", ondelete="CASCADE"), nullable=True)
    observable = relationship("Observable", backref="webhook_deliveries")
    
    alert_id = Column(Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=True)
    alert = relationship("Alert", backref="webhook_deliveries")
    
    # Relationships
    webhook_id = Column(Integer, ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False)
    webhook = relationship("Webhook", back_populates="deliveries")

    __table_args__ = (
        Index('idx_delivery_webhook_status', 'webhook_id', 'status'),
        Index('idx_delivery_event_created', 'event_type', 'created_at'),
        Index('idx_delivery_next_retry', 'next_retry_at'),
        Index('idx_delivery_case', 'case_id'),
        Index('idx_delivery_triggered_by', 'triggered_by_id'),
    )

    def __repr__(self):
        return f"<WebhookDelivery webhook={self.webhook.name} event={self.event_type} status={self.status}>"


class WebhookTemplate(Base, UUIDMixin, TimestampMixin):
    """Predefined webhook templates for common integrations"""
    __tablename__ = "webhook_templates"

    name = Column(String(255), nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=False)  # 'chat', 'ticketing', 'siem', etc.
    
    # Template configuration
    url_template = Column(String(500), nullable=False)  # Can contain placeholders
    method = Column(String(10), default="POST", nullable=False)
    headers_template = Column(JSON, default=dict, nullable=False)
    body_template = Column(Text, nullable=False)  # Jinja2 template
    
    # Supported events
    supported_events = Column(JSON, nullable=False)
    
    # Configuration schema for user inputs
    config_schema = Column(JSON, default=dict, nullable=False)  # JSON schema
    
    # Usage statistics
    usage_count = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index('idx_template_category', 'category'),
        Index('idx_template_active', 'is_active'),
    )

    def __repr__(self):
        return f"<WebhookTemplate name={self.name} category={self.category}>"