# app/db/models/enums.py
import enum


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
    OPEN = "Open"
    RESOLVED = "Resolved"
    DUPLICATED = "Duplicated"


class ResolutionStatus(str, enum.Enum):
    """Case resolution status matching TheHive 4.1.24"""
    INDETERMINATE = "Indeterminate"
    FALSE_POSITIVE = "FalsePositive"
    TRUE_POSITIVE = "TruePositive"
    OTHER = "Other"
    DUPLICATED = "Duplicated"


class ImpactStatus(str, enum.Enum):
    """Case impact status matching TheHive 4.1.24"""
    NO_IMPACT = "NoImpact"
    WITH_IMPACT = "WithImpact"
    NOT_APPLICABLE = "NotApplicable"


class TaskStatus(str, enum.Enum):
    WAITING = "Waiting"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"
    CANCEL = "Cancel"


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