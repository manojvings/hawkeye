# app/utils/helpers.py
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Union
import re
import json
from loguru import logger


def utc_now() -> datetime:
    """Get current UTC datetime"""
    return datetime.now(timezone.utc)


def format_datetime(dt: datetime) -> str:
    """Format datetime for API responses"""
    return dt.isoformat()


def sanitize_email(email: str) -> str:
    """Sanitize email address"""
    return email.lower().strip()


def mask_sensitive_data(data: str, visible_chars: int = 4, mask_char: str = "*") -> str:
    """
    Mask sensitive data for logging

    Args:
        data: The sensitive data to mask
        visible_chars: Number of characters to show at the beginning
        mask_char: Character to use for masking
    """
    if not data or len(data) <= visible_chars:
        return mask_char * len(data) if data else ""

    return data[:visible_chars] + mask_char * (len(data) - visible_chars)


def generate_user_display_name(email: str) -> str:
    """Generate display name from email"""
    return email.split('@')[0].title()


def is_valid_uuid(uuid_string: str) -> bool:
    """Check if string is valid UUID"""
    import uuid
    try:
        uuid.UUID(uuid_string)
        return True
    except ValueError:
        return False


def clean_dict(data: Dict[str, Any], remove_none: bool = True, remove_empty: bool = False) -> Dict[str, Any]:
    """
    Clean dictionary by removing None values and optionally empty values

    Args:
        data: Dictionary to clean
        remove_none: Remove None values
        remove_empty: Remove empty strings, lists, dicts
    """
    cleaned = {}

    for key, value in data.items():
        if remove_none and value is None:
            continue
        if remove_empty and value in ("", [], {}):
            continue
        cleaned[key] = value

    return cleaned


def safe_json_dumps(data: Any, indent: Optional[int] = None) -> str:
    """Safely serialize data to JSON"""
    try:
        return json.dumps(data, default=str, indent=indent)
    except Exception as e:
        logger.warning(f"Failed to serialize data to JSON: {e}")
        return "{}"


def safe_json_loads(data: str) -> Optional[Dict[str, Any]]:
    """Safely deserialize JSON data"""
    try:
        return json.loads(data)
    except Exception as e:
        logger.warning(f"Failed to deserialize JSON data: {e}")
        return None


def extract_domain_from_email(email: str) -> str:
    """Extract domain from email address"""
    return email.split('@')[1].lower() if '@' in email else ""


def generate_random_string(length: int = 32) -> str:
    """Generate random string for tokens, IDs, etc."""
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate string to specified length"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def bytes_to_human_readable(bytes_count: int) -> str:
    """Convert bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_count < 1024.0:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.1f} PB"