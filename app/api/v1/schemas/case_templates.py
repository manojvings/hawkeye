# app/api/v1/schemas/case_templates.py
from pydantic import BaseModel, Field, UUID4, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from app.db.models.enums import Severity, TLP


class TaskTemplateBase(BaseModel):
    """Base schema for task template"""
    title: str = Field(..., min_length=1, max_length=500, description="Task template title")
    description: Optional[str] = Field(None, description="Task template description")
    group: str = Field("default", max_length=100, description="Task group for organization")
    order_index: int = Field(0, ge=0, description="Order within template")
    flag: bool = Field(False, description="Default flag status")
    assignee_role: Optional[str] = Field(None, max_length=50, description="Role to assign task to")
    due_days_offset: Optional[int] = Field(None, ge=0, description="Days offset from case creation for due date")
    depends_on: List[UUID4] = Field(default_factory=list, description="Task template dependencies")


class TaskTemplateCreate(TaskTemplateBase):
    """Schema for creating a task template"""
    pass


class TaskTemplateUpdate(BaseModel):
    """Schema for updating a task template"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    group: Optional[str] = Field(None, max_length=100)
    order_index: Optional[int] = Field(None, ge=0)
    flag: Optional[bool] = None
    assignee_role: Optional[str] = Field(None, max_length=50)
    due_days_offset: Optional[int] = Field(None, ge=0)
    depends_on: Optional[List[UUID4]] = None


class TaskTemplateResponse(TaskTemplateBase):
    """Schema for task template response"""
    id: UUID4 = Field(..., description="Task template UUID")
    case_template_id: UUID4 = Field(..., description="Case template UUID")
    created_by_id: UUID4 = Field(..., description="Creator UUID")
    created_by_email: str = Field(..., description="Creator email")
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, task_template):
        """Convert TaskTemplate model to API response"""
        return cls(
            id=task_template.uuid,
            title=task_template.title,
            description=task_template.description,
            group=task_template.group,
            order_index=task_template.order_index,
            flag=task_template.flag,
            assignee_role=task_template.assignee_role,
            due_days_offset=task_template.due_days_offset,
            depends_on=task_template.depends_on or [],
            case_template_id=task_template.case_template.uuid,
            created_by_id=task_template.created_by.uuid,
            created_by_email=task_template.created_by.email,
            created_at=task_template.created_at,
            updated_at=task_template.updated_at
        )

    class Config:
        from_attributes = True


class CaseTemplateBase(BaseModel):
    """Base schema for case template"""
    name: str = Field(..., min_length=1, max_length=255, description="Template unique name")
    display_name: str = Field(..., min_length=1, max_length=255, description="Template display name")
    title_prefix: Optional[str] = Field(None, max_length=100, description="Prefix for case titles")
    description: Optional[str] = Field(None, description="Template description")
    severity: Optional[Severity] = Field(None, description="Default case severity")
    tlp: Optional[TLP] = Field(TLP.AMBER, description="Default TLP level")
    pap: Optional[TLP] = Field(TLP.AMBER, description="Default PAP level")
    flag: bool = Field(False, description="Default flag status")
    tags: List[str] = Field(default_factory=list, description="Default case tags")
    custom_fields: Dict[str, Any] = Field(default_factory=dict, description="Default custom fields")
    summary: Optional[str] = Field(None, description="Default case summary template")

    @validator('tags')
    def validate_tags(cls, v):
        """Validate and clean tags"""
        if v is None:
            return []
        # Remove duplicates and empty tags
        return list(set(tag.strip() for tag in v if tag.strip()))


class CaseTemplateCreate(CaseTemplateBase):
    """Schema for creating a case template"""
    task_templates: List[TaskTemplateCreate] = Field(default_factory=list, description="Task templates")

    @validator('name')
    def validate_name(cls, v):
        """Validate template name"""
        # Template name should be alphanumeric with underscores/hyphens
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("Template name must contain only alphanumeric characters, underscores, and hyphens")
        return v.lower()


class CaseTemplateUpdate(BaseModel):
    """Schema for updating a case template"""
    display_name: Optional[str] = Field(None, min_length=1, max_length=255)
    title_prefix: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    severity: Optional[Severity] = None
    tlp: Optional[TLP] = None
    pap: Optional[TLP] = None
    flag: Optional[bool] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    is_active: Optional[bool] = None

    @validator('tags')
    def validate_tags(cls, v):
        """Validate and clean tags"""
        if v is None:
            return v
        # Remove duplicates and empty tags
        return list(set(tag.strip() for tag in v if tag.strip()))


class CaseTemplateResponse(CaseTemplateBase):
    """Schema for case template response"""
    id: UUID4 = Field(..., description="Case template UUID")
    is_active: bool = Field(..., description="Template active status")
    usage_count: int = Field(..., description="Template usage count")
    organization_id: UUID4 = Field(..., description="Organization UUID")
    organization_name: str = Field(..., description="Organization name")
    created_by_id: UUID4 = Field(..., description="Creator UUID")
    created_by_email: str = Field(..., description="Creator email")
    created_at: datetime
    updated_at: datetime
    task_templates: List[TaskTemplateResponse] = Field(default_factory=list, description="Associated task templates")

    @classmethod
    def from_model(cls, case_template, include_tasks: bool = True):
        """Convert CaseTemplate model to API response"""
        return cls(
            id=case_template.uuid,
            name=case_template.name,
            display_name=case_template.display_name,
            title_prefix=case_template.title_prefix,
            description=case_template.description,
            severity=case_template.severity.value if case_template.severity else None,
            tlp=case_template.tlp.value if case_template.tlp else None,
            pap=case_template.pap.value if case_template.pap else None,
            flag=case_template.flag,
            tags=case_template.tags or [],
            custom_fields=case_template.custom_fields or {},
            summary=case_template.summary,
            is_active=case_template.is_active,
            usage_count=case_template.usage_count,
            organization_id=case_template.organization.uuid,
            organization_name=case_template.organization.name,
            created_by_id=case_template.created_by.uuid,
            created_by_email=case_template.created_by.email,
            created_at=case_template.created_at,
            updated_at=case_template.updated_at,
            task_templates=[
                TaskTemplateResponse.from_model(task) 
                for task in sorted(case_template.task_templates, key=lambda t: t.order_index)
            ] if include_tasks else []
        )

    class Config:
        from_attributes = True


class CaseTemplateSummary(BaseModel):
    """Lightweight case template summary for lists"""
    id: UUID4
    name: str
    display_name: str
    description: Optional[str]
    is_active: bool
    usage_count: int
    task_count: int = Field(0, description="Number of task templates")
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, case_template):
        """Convert CaseTemplate model to summary"""
        return cls(
            id=case_template.uuid,
            name=case_template.name,
            display_name=case_template.display_name,
            description=case_template.description,
            is_active=case_template.is_active,
            usage_count=case_template.usage_count,
            task_count=len(case_template.task_templates),
            created_at=case_template.created_at,
            updated_at=case_template.updated_at
        )

    class Config:
        from_attributes = True


class CaseFromTemplateRequest(BaseModel):
    """Schema for creating a case from a template"""
    template_id: UUID4 = Field(..., description="Case template UUID")
    title: str = Field(..., min_length=1, max_length=500, description="Case title")
    description: Optional[str] = Field(None, description="Case description (overrides template)")
    severity: Optional[Severity] = Field(None, description="Case severity (overrides template)")
    tlp: Optional[TLP] = Field(None, description="Case TLP (overrides template)")
    assignee_email: Optional[str] = Field(None, description="Email of user to assign case to")
    additional_tags: List[str] = Field(default_factory=list, description="Additional tags to add")
    custom_field_overrides: Dict[str, Any] = Field(default_factory=dict, description="Custom field overrides")
    create_tasks: bool = Field(True, description="Whether to create tasks from template")

    @validator('additional_tags')
    def validate_additional_tags(cls, v):
        """Validate and clean additional tags"""
        if v is None:
            return []
        return list(set(tag.strip() for tag in v if tag.strip()))


class TemplateUsageStats(BaseModel):
    """Template usage statistics"""
    template_id: UUID4
    template_name: str
    usage_count: int
    last_used: Optional[datetime] = Field(None, description="Last time template was used")
    cases_created: int = Field(0, description="Total cases created from template")
    avg_case_duration: Optional[float] = Field(None, description="Average case duration in days")


class BulkTemplateOperation(BaseModel):
    """Schema for bulk template operations"""
    template_ids: List[UUID4] = Field(..., description="List of template UUIDs")
    operation: str = Field(..., description="Operation to perform")
    
    @validator('template_ids')
    def validate_template_ids(cls, v):
        """Ensure at least one template ID"""
        if not v:
            raise ValueError("At least one template ID is required")
        return v

    @validator('operation')
    def validate_operation(cls, v):
        """Validate operation type"""
        allowed_operations = ['activate', 'deactivate', 'delete']
        if v not in allowed_operations:
            raise ValueError(f"Operation must be one of: {', '.join(allowed_operations)}")
        return v