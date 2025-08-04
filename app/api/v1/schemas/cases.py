# app/api/v1/schemas/cases.py
from pydantic import BaseModel, Field, UUID4, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# Import enums (or redefine if needed)
class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TLP(str, Enum):
    WHITE = "white"
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class CaseStatus(str, Enum):
    OPEN = "Open"
    RESOLVED = "Resolved"
    DUPLICATED = "Duplicated"


class ResolutionStatus(str, Enum):
    INDETERMINATE = "Indeterminate"
    FALSE_POSITIVE = "FalsePositive"
    TRUE_POSITIVE = "TruePositive"
    OTHER = "Other"
    DUPLICATED = "Duplicated"


class ImpactStatus(str, Enum):
    NO_IMPACT = "NoImpact"
    WITH_IMPACT = "WithImpact"
    NOT_APPLICABLE = "NotApplicable"


class CaseBase(BaseModel):
    """Base schema for case"""
    title: str = Field(..., min_length=1, max_length=500, description="Case title")
    description: Optional[str] = Field(None, description="Case description")
    severity: Severity = Field(Severity.MEDIUM, description="Case severity")
    tlp: TLP = Field(TLP.AMBER, description="Traffic Light Protocol level")
    tags: List[str] = Field(default_factory=list, description="Case tags")
    custom_fields: Dict[str, Any] = Field(default_factory=dict, description="Custom fields")
    due_date: Optional[datetime] = Field(None, description="Due date for the case")
    summary: Optional[str] = Field(None, description="Case closure summary")
    impact_status: Optional[ImpactStatus] = Field(None, description="Case impact assessment")
    resolution_status: Optional[ResolutionStatus] = Field(None, description="Case resolution classification")
    case_template: Optional[str] = Field(None, max_length=100, description="Template used for case creation")


class CaseCreate(CaseBase):
    """Schema for creating a case"""
    assignee_email: Optional[str] = Field(None, description="Email of user to assign")


class CaseUpdate(BaseModel):
    """Schema for updating a case"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    severity: Optional[Severity] = None
    tlp: Optional[TLP] = None
    status: Optional[CaseStatus] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[Dict[str, Any]] = None
    due_date: Optional[datetime] = None
    assignee_email: Optional[str] = Field(None, description="Email of user to assign (null to unassign)")
    summary: Optional[str] = None
    impact_status: Optional[ImpactStatus] = None
    resolution_status: Optional[ResolutionStatus] = None
    case_template: Optional[str] = Field(None, max_length=100)


class CaseResponse(CaseBase):
    """Schema for case response with UUID"""
    id: UUID4 = Field(..., description="Case UUID")
    case_number: str = Field(..., description="Unique case number")
    status: CaseStatus = Field(..., description="Case status")
    organization_id: UUID4 = Field(..., description="Organization UUID")
    assignee_id: Optional[UUID4] = Field(None, description="Assignee UUID")
    assignee_email: Optional[str] = Field(None, description="Assignee email")
    created_by_id: UUID4 = Field(..., description="Creator UUID")
    created_by_email: str = Field(..., description="Creator email")
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None
    task_count: Optional[int] = Field(0, description="Number of tasks")
    observable_count: Optional[int] = Field(0, description="Number of observables")

    @classmethod
    def from_model(cls, case, task_count: int = 0, observable_count: int = 0):
        """Convert Case model to API response using UUID"""
        return cls(
            id=case.uuid,
            case_number=case.case_number,
            title=case.title,
            description=case.description,
            severity=case.severity.value,
            tlp=case.tlp.value,
            status=case.status.value,
            tags=case.tags or [],
            custom_fields=case.custom_fields or {},
            due_date=case.due_date,
            summary=case.summary,
            impact_status=case.impact_status.value if case.impact_status else None,
            resolution_status=case.resolution_status.value if case.resolution_status else None,
            case_template=case.case_template,
            organization_id=case.organization.uuid,
            assignee_id=case.assignee.uuid if case.assignee else None,
            assignee_email=case.assignee.email if case.assignee else None,
            created_by_id=case.created_by.uuid,
            created_by_email=case.created_by.email,
            created_at=case.created_at,
            updated_at=case.updated_at,
            closed_at=case.closed_at,
            task_count=task_count,
            observable_count=observable_count
        )

    class Config:
        from_attributes = True


class CaseStatusUpdate(BaseModel):
    """Schema for updating case status with validation"""
    status: CaseStatus = Field(..., description="New case status")
    resolution_notes: Optional[str] = Field(None, description="Notes when resolving/closing case")


class CaseSummary(BaseModel):
    """Lightweight case summary for lists"""
    id: UUID4
    case_number: str
    title: str
    severity: Severity
    status: CaseStatus
    assignee_email: Optional[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, case):
        """Convert Case model to summary"""
        return cls(
            id=case.uuid,
            case_number=case.case_number,
            title=case.title,
            severity=case.severity.value,
            status=case.status.value,
            assignee_email=case.assignee.email if case.assignee else None,
            created_at=case.created_at,
            updated_at=case.updated_at
        )

    class Config:
        from_attributes = True