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