# app/db/models/__init__.py
"""
Database models package
Imports all models for easy access
"""

# Import base classes and mixins
from app.db.models.base import Base, TimestampMixin, UUIDMixin

# Import all enums
from app.db.models.enums import (
    Severity, TLP, CaseStatus, TaskStatus,
    AlertStatus, UserRole, ObservableType
)

# Import authentication models
from app.db.models.auth import User, RefreshToken, BlacklistedToken

# Import API key model
from app.db.models.api_key import APIKey

# Import organization models
from app.db.models.organization import Organization, UserOrganization

# Import SIRP models
from app.db.models.case import Case
from app.db.models.task import Task
from app.db.models.observable import Observable
from app.db.models.alert import Alert

# Export all models and enums
__all__ = [
    # Base classes
    'Base', 'TimestampMixin', 'UUIDMixin',

    # Enums
    'Severity', 'TLP', 'CaseStatus', 'TaskStatus',
    'AlertStatus', 'UserRole', 'ObservableType',

    # Authentication models
    'User', 'RefreshToken', 'BlacklistedToken',

    # API management
    'APIKey',

    # Organization models
    'Organization', 'UserOrganization',

    # SIRP models
    'Case', 'Task', 'Observable', 'Alert',
]
