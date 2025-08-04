# app/utils/validators.py
import re
from typing import Optional, Tuple, List
from datetime import datetime
import ipaddress


class PasswordValidator:
    """Password validation utilities"""

    MIN_LENGTH = 8
    MAX_LENGTH = 64

    @classmethod
    def validate_complexity(cls, password: str) -> Tuple[bool, Optional[str]]:
        """
        Validate password complexity
        Returns (is_valid, error_message)
        """
        if len(password) < cls.MIN_LENGTH:
            return False, f"Password must be at least {cls.MIN_LENGTH} characters long"

        if len(password) > cls.MAX_LENGTH:
            return False, f"Password must be less than {cls.MAX_LENGTH} characters long"

        if not re.search(r"[a-z]", password):
            return False, "Password must contain at least one lowercase letter"

        if not re.search(r"[A-Z]", password):
            return False, "Password must contain at least one uppercase letter"

        if not re.search(r"\d", password):
            return False, "Password must contain at least one digit"

        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
            return False, "Password must contain at least one special character"

        return True, None

    @classmethod
    def get_strength_score(cls, password: str) -> int:
        """
        Calculate password strength score (0-100)
        """
        score = 0

        # Length scoring
        if len(password) >= 8:
            score += 20
        if len(password) >= 12:
            score += 10
        if len(password) >= 16:
            score += 10

        # Character variety scoring
        if re.search(r"[a-z]", password):
            score += 15
        if re.search(r"[A-Z]", password):
            score += 15
        if re.search(r"\d", password):
            score += 15
        if re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
            score += 15

        return min(score, 100)


class EmailValidator:
    """Email validation utilities"""

    # Common disposable email domains
    DISPOSABLE_DOMAINS = {
        "10minutemail.com", "tempmail.org", "guerrillamail.com",
        "mailinator.com", "throwaway.email", "temp-mail.org",
        "yopmail.com", "maildrop.cc", "tempmail.net"
    }

    @classmethod
    def is_disposable_email(cls, email: str) -> bool:
        """Check if email is from disposable email provider"""
        domain = email.split('@')[1].lower() if '@' in email else ""
        return domain in cls.DISPOSABLE_DOMAINS

    @classmethod
    def normalize_email(cls, email: str) -> str:
        """Normalize email address"""
        return email.lower().strip()

    @classmethod
    def is_valid_format(cls, email: str) -> bool:
        """Validate email format using regex"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @classmethod
    def extract_domain(cls, email: str) -> str:
        """Extract domain from email"""
        return email.split('@')[1].lower() if '@' in email else ""


class IPValidator:
    """IP address validation utilities"""

    @staticmethod
    def is_private_ip(ip: str) -> bool:
        """Check if IP is private/internal"""
        try:
            ip_obj = ipaddress.ip_address(ip)
            return ip_obj.is_private
        except ValueError:
            return False

    @staticmethod
    def is_valid_ip(ip: str) -> bool:
        """Check if IP address is valid"""
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False

    @staticmethod
    def get_ip_version(ip: str) -> Optional[int]:
        """Get IP version (4 or 6)"""
        try:
            ip_obj = ipaddress.ip_address(ip)
            return ip_obj.version
        except ValueError:
            return None


class DataValidator:
    """General data validation utilities"""

    @staticmethod
    def is_valid_phone(phone: str, country_code: str = "US") -> bool:
        """Validate phone number format"""
        # Basic validation - can be enhanced with phonenumbers library
        cleaned = re.sub(r'[^\d+]', '', phone)
        return len(cleaned) >= 10 and len(cleaned) <= 15

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Validate URL format"""
        pattern = r'^https?://(?:[-\w.])+(?:\:[0-9]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:[\w.])*)?)?$'
        return bool(re.match(pattern, url))

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename for safe storage"""
        # Remove or replace dangerous characters
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
        return sanitized.strip('. ')

    @staticmethod
    def validate_date_range(start_date: datetime, end_date: datetime) -> bool:
        """Validate that start_date is before end_date"""
        return start_date < end_date

    @staticmethod
    def is_valid_json(json_string: str) -> bool:
        """Check if string is valid JSON"""
        import json
        try:
            json.loads(json_string)
            return True
        except (json.JSONDecodeError, TypeError):
            return False
