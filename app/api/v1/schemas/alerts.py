# app/api/v1/schemas/alerts.py
from pydantic import BaseModel, Field, UUID4, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class AlertStatus(str, Enum):
    """Alert status enumeration"""
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    IMPORTED = "imported"
    IGNORED = "ignored"


class Severity(str, Enum):
    """Severity enumeration"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TLP(str, Enum):
    """Traffic Light Protocol levels"""
    WHITE = "white"
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class AlertObservable(BaseModel):
    """Embedded observable data in alerts"""
    data_type: str = Field(..., description="Type of observable")
    data: str = Field(..., description="Observable value")
    is_ioc: bool = Field(False, description="Whether this is an IOC")
    tags: List[str] = Field(default_factory=list, description="Observable tags")

    @validator('data')
    def validate_data(cls, v):
        """Validate and clean data"""
        return v.strip()


class AlertBase(BaseModel):
    """Base schema for alert"""
    type: str = Field(..., min_length=1, max_length=100, description="Alert type")
    title: str = Field(..., min_length=1, max_length=500, description="Alert title")
    description: Optional[str] = Field(None, description="Alert description")
    source: str = Field(..., min_length=1, max_length=255, description="Source system")
    source_ref: str = Field(..., min_length=1, max_length=255, description="Source reference ID")
    external_link: Optional[str] = Field(None, max_length=1000, description="Link to source system")
    severity: Severity = Field(Severity.MEDIUM, description="Alert severity")
    tlp: TLP = Field(TLP.AMBER, description="Traffic Light Protocol level")
    pap: TLP = Field(TLP.AMBER, description="Permissible Actions Protocol level")
    date: datetime = Field(..., description="Alert occurrence date")
    last_sync_date: datetime = Field(..., description="Last sync from source")
    read: bool = Field(False, description="Has been read")
    follow: bool = Field(False, description="Follow for updates")
    tags: List[str] = Field(default_factory=list, description="Alert tags")
    raw_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Raw alert data")
    observables: Optional[List[AlertObservable]] = Field(default_factory=list, description="Embedded observables")


class AlertCreate(AlertBase):
    """Schema for creating an alert"""
    pass


class AlertUpdate(BaseModel):
    """Schema for updating an alert"""
    type: Optional[str] = Field(None, min_length=1, max_length=100)
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    external_link: Optional[str] = Field(None, max_length=1000)
    severity: Optional[Severity] = None
    tlp: Optional[TLP] = None
    pap: Optional[TLP] = None
    status: Optional[AlertStatus] = None
    date: Optional[datetime] = None
    last_sync_date: Optional[datetime] = None
    read: Optional[bool] = None
    follow: Optional[bool] = None
    tags: Optional[List[str]] = None
    raw_data: Optional[Dict[str, Any]] = None
    observables: Optional[List[AlertObservable]] = None


class AlertResponse(AlertBase):
    """Schema for alert response with UUID"""
    id: UUID4 = Field(..., description="Alert UUID")
    status: AlertStatus = Field(..., description="Alert status")
    organization_id: UUID4 = Field(..., description="Organization UUID")
    case_id: Optional[UUID4] = Field(None, description="Associated case UUID if imported")
    case_number: Optional[str] = Field(None, description="Associated case number if imported")
    created_by_id: Optional[UUID4] = Field(None, description="Creator UUID")
    created_by_email: Optional[str] = Field(None, description="Creator email")
    created_at: datetime
    updated_at: datetime
    imported_at: Optional[datetime] = Field(None, description="When alert was imported to case")

    @classmethod
    def from_model(cls, alert):
        """Convert Alert model to API response using UUID"""
        return cls(
            id=alert.uuid,
            type=alert.type,
            title=alert.title,
            description=alert.description,
            source=alert.source,
            source_ref=alert.source_ref,
            external_link=alert.external_link,
            severity=alert.severity.value,
            tlp=alert.tlp.value,
            pap=alert.pap.value,
            status=alert.status.value,
            date=alert.date,
            last_sync_date=alert.last_sync_date,
            read=alert.read,
            follow=alert.follow,
            tags=alert.tags or [],
            raw_data=alert.raw_data or {},
            observables=[
                AlertObservable(**obs) if isinstance(obs, dict) else obs 
                for obs in (alert.observables or [])
            ],
            organization_id=alert.organization.uuid,
            case_id=alert.case.uuid if alert.case else None,
            case_number=alert.case.case_number if alert.case else None,
            created_by_id=alert.created_by.uuid if alert.created_by else None,
            created_by_email=alert.created_by.email if alert.created_by else None,
            created_at=alert.created_at,
            updated_at=alert.updated_at,
            imported_at=alert.imported_at
        )

    class Config:
        from_attributes = True


class AlertSummary(BaseModel):
    """Lightweight alert summary for lists"""
    id: UUID4
    title: str
    source: str
    source_ref: str
    severity: Severity
    status: AlertStatus
    observable_count: int = Field(0, description="Number of observables")
    created_at: datetime
    imported_at: Optional[datetime] = None

    @classmethod
    def from_model(cls, alert):
        """Convert Alert model to summary"""
        return cls(
            id=alert.uuid,
            title=alert.title,
            source=alert.source,
            source_ref=alert.source_ref,
            severity=alert.severity.value,
            status=alert.status.value,
            observable_count=len(alert.observables or []),
            created_at=alert.created_at,
            imported_at=alert.imported_at
        )

    class Config:
        from_attributes = True


class AlertPromotionRequest(BaseModel):
    """Schema for promoting alert to case"""
    case_title: Optional[str] = Field(None, description="Custom case title (uses alert title if not provided)")
    case_description: Optional[str] = Field(None, description="Custom case description")
    assignee_email: Optional[str] = Field(None, description="Email of user to assign case to")


class BulkAlertStatusUpdate(BaseModel):
    """Schema for bulk status update"""
    alert_ids: List[UUID4] = Field(..., description="List of alert UUIDs to update")
    status: AlertStatus = Field(..., description="New status for all alerts")

    @validator('alert_ids')
    def validate_alert_ids(cls, v):
        """Ensure at least one alert ID"""
        if not v:
            raise ValueError("At least one alert ID is required")
        return v


class AlertAcknowledgmentRequest(BaseModel):
    """Schema for acknowledging an alert"""
    notes: Optional[str] = Field(None, description="Optional acknowledgment notes")


class AlertIgnoreRequest(BaseModel):
    """Schema for ignoring an alert"""
    reason: Optional[str] = Field(None, description="Reason for ignoring the alert")


class AlertStats(BaseModel):
    """Alert statistics for an organization"""
    total: int = Field(..., description="Total number of alerts")
    new: int = Field(..., description="Number of new alerts")
    acknowledged: int = Field(..., description="Number of acknowledged alerts")
    imported: int = Field(..., description="Number of imported alerts")
    ignored: int = Field(..., description="Number of ignored alerts")

    @property
    def pending_percentage(self) -> float:
        """Calculate percentage of pending (new + acknowledged) alerts"""
        if self.total == 0:
            return 0.0
        pending = self.new + self.acknowledged
        return (pending / self.total) * 100


class AlertSourceSummary(BaseModel):
    """Alert summary by source"""
    source: str = Field(..., description="Source system name")
    total_alerts: int = Field(..., description="Total alerts from this source")
    new_alerts: int = Field(..., description="New alerts from this source")
    last_alert_at: Optional[datetime] = Field(None, description="When last alert was received")


class AlertSearchRequest(BaseModel):
    """Schema for alert search"""
    search_term: str = Field(..., min_length=1, description="Search term")
    status_filter: Optional[AlertStatus] = Field(None, description="Filter by status")
    severity_filter: Optional[Severity] = Field(None, description="Filter by severity")
    source_filter: Optional[str] = Field(None, description="Filter by source")
    date_from: Optional[datetime] = Field(None, description="Filter alerts from this date")
    date_to: Optional[datetime] = Field(None, description="Filter alerts to this date")


class AlertImportResult(BaseModel):
    """Result of alert import/ingestion"""
    success: bool = Field(..., description="Whether import was successful")
    alert_id: Optional[UUID4] = Field(None, description="Alert UUID if created")
    message: str = Field(..., description="Result message")
    duplicate: bool = Field(False, description="Whether alert was a duplicate")
    existing_alert_id: Optional[UUID4] = Field(None, description="Existing alert UUID if duplicate")


class AlertEnrichmentData(BaseModel):
    """Alert enrichment information"""
    alert: AlertResponse
    similar_alerts: List[AlertSummary] = Field(default_factory=list)
    related_cases: List[str] = Field(default_factory=list, description="Related case numbers")
    observable_enrichment: Dict[str, Any] = Field(default_factory=dict, description="Observable analysis results")
    threat_intelligence: Dict[str, Any] = Field(default_factory=dict, description="Threat intel matches")


class AlertTriage(BaseModel):
    """Alert triage information"""
    alert_id: UUID4 = Field(..., description="Alert UUID")
    recommendation: str = Field(..., description="Triage recommendation")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    reasons: List[str] = Field(default_factory=list, description="Reasons for recommendation")
    risk_score: int = Field(..., ge=0, le=100, description="Risk score")
    suggested_actions: List[str] = Field(default_factory=list, description="Suggested next actions")