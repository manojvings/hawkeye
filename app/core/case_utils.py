# app/core/case_utils.py
"""
Utilities for case management including case number generation
"""
from datetime import datetime
from typing import Optional
import random
import string


class CaseNumberGenerator:
    """Generate unique case numbers following TheHive pattern"""

    @staticmethod
    def generate_case_number(organization_name: str, timestamp: Optional[datetime] = None) -> str:
        """
        Generate a unique case number.
        Format: ORG-YYYYMMDD-XXXX
        Example: SEC-20240115-A7B3

        Args:
            organization_name: Name of the organization
            timestamp: Optional timestamp (defaults to now)

        Returns:
            Unique case number string
        """
        if not timestamp:
            timestamp = datetime.utcnow()

        # Get first 3 letters of org name (uppercase)
        org_prefix = ''.join(c for c in organization_name.upper() if c.isalpha())[:3]
        if len(org_prefix) < 3:
            org_prefix = org_prefix.ljust(3, 'X')

        # Format date
        date_part = timestamp.strftime('%Y%m%d')

        # Generate random suffix (4 alphanumeric characters)
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

        return f"{org_prefix}-{date_part}-{suffix}"


# Case status transition validator
class CaseStatusTransition:
    """Validate case status transitions"""

    VALID_TRANSITIONS = {
        'open': ['in_progress', 'resolved', 'closed'],
        'in_progress': ['open', 'resolved', 'closed'],
        'resolved': ['open', 'in_progress', 'closed'],
        'closed': []  # Cannot reopen closed cases
    }

    @classmethod
    def is_valid_transition(cls, current_status: str, new_status: str) -> bool:
        """Check if a status transition is valid"""
        return new_status in cls.VALID_TRANSITIONS.get(current_status, [])

    @classmethod
    def get_allowed_transitions(cls, current_status: str) -> list:
        """Get list of allowed status transitions"""
        return cls.VALID_TRANSITIONS.get(current_status, [])


# Task status transition validator
class TaskStatusTransition:
    """Validate task status transitions"""

    VALID_TRANSITIONS = {
        'pending': ['in_progress', 'completed', 'cancelled'],
        'in_progress': ['pending', 'completed', 'cancelled'],
        'completed': ['in_progress'],  # Can reopen completed tasks
        'cancelled': ['pending', 'in_progress']
    }

    @classmethod
    def is_valid_transition(cls, current_status: str, new_status: str) -> bool:
        """Check if a status transition is valid"""
        return new_status in cls.VALID_TRANSITIONS.get(current_status, [])

    @classmethod
    def get_allowed_transitions(cls, current_status: str) -> list:
        """Get list of allowed status transitions"""
        return cls.VALID_TRANSITIONS.get(current_status, [])