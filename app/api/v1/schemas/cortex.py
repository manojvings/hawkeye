# app/api/v1/schemas/cortex.py
"""Pydantic schemas for Cortex integration"""
from pydantic import BaseModel, Field, UUID4, validator, HttpUrl
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from app.db.models.enums import JobStatus, WorkerType


class CortexInstanceBase(BaseModel):
    """Base schema for Cortex instance"""
    name: str = Field(..., min_length=1, max_length=255, description="Instance name")
    url: HttpUrl = Field(..., description="Cortex instance URL")
    enabled: bool = Field(True, description="Instance enabled status")
    included_organizations: List[str] = Field(default_factory=lambda: ["*"], description="Included organizations")
    excluded_organizations: List[str] = Field(default_factory=list, description="Excluded organizations")
    verify_ssl: bool = Field(True, description="Verify SSL certificates")
    timeout: int = Field(60, ge=10, le=300, description="Request timeout in seconds")
    max_concurrent_jobs: int = Field(10, ge=1, le=100, description="Maximum concurrent jobs")


class CortexInstanceCreate(CortexInstanceBase):
    """Schema for creating Cortex instance"""
    api_key: str = Field(..., min_length=1, description="Cortex API key")
    
    @validator('name')
    def validate_name(cls, v):
        """Validate instance name"""
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("Instance name must contain only alphanumeric characters, underscores, and hyphens")
        return v.lower()


class CortexInstanceUpdate(BaseModel):
    """Schema for updating Cortex instance"""
    url: Optional[HttpUrl] = None
    api_key: Optional[str] = Field(None, min_length=1)
    enabled: Optional[bool] = None
    included_organizations: Optional[List[str]] = None
    excluded_organizations: Optional[List[str]] = None
    verify_ssl: Optional[bool] = None
    timeout: Optional[int] = Field(None, ge=10, le=300)
    max_concurrent_jobs: Optional[int] = Field(None, ge=1, le=100)


class CortexInstanceResponse(CortexInstanceBase):
    """Schema for Cortex instance response"""
    id: UUID4 = Field(..., description="Instance UUID")
    version: Optional[str] = Field(None, description="Cortex version")
    created_at: datetime
    updated_at: datetime
    
    # Statistics
    analyzer_count: int = Field(0, description="Number of analyzers")
    responder_count: int = Field(0, description="Number of responders")
    active_jobs: int = Field(0, description="Number of active jobs")

    @classmethod
    def from_model(cls, instance, analyzer_count: int = 0, responder_count: int = 0, active_jobs: int = 0):
        """Convert CortexInstance model to API response"""
        return cls(
            id=instance.uuid,
            name=instance.name,
            url=instance.url,
            enabled=instance.enabled,
            included_organizations=instance.included_organizations,
            excluded_organizations=instance.excluded_organizations,
            verify_ssl=instance.verify_ssl,
            timeout=instance.timeout,
            max_concurrent_jobs=instance.max_concurrent_jobs,
            version=instance.version,
            created_at=instance.created_at,
            updated_at=instance.updated_at,
            analyzer_count=analyzer_count,
            responder_count=responder_count,
            active_jobs=active_jobs
        )

    class Config:
        from_attributes = True


class CortexWorkerBase(BaseModel):
    """Base schema for Cortex worker (analyzer/responder)"""
    name: str = Field(..., description="Worker name")
    display_name: str = Field(..., description="Worker display name")
    version: str = Field(..., description="Worker version")
    description: Optional[str] = Field(None, description="Worker description")
    data_types: List[str] = Field(..., description="Supported data types")
    max_tlp: int = Field(3, ge=0, le=3, description="Maximum TLP level")
    max_pap: int = Field(3, ge=0, le=3, description="Maximum PAP level")
    enabled: bool = Field(True, description="Worker enabled status")
    configuration: Dict[str, Any] = Field(default_factory=dict, description="Worker configuration")


class CortexAnalyzerResponse(CortexWorkerBase):
    """Schema for Cortex analyzer response"""
    id: UUID4 = Field(..., description="Analyzer UUID")
    cortex_instance_id: UUID4 = Field(..., description="Cortex instance UUID")
    cortex_instance_name: str = Field(..., description="Cortex instance name")
    rate_limit: Optional[int] = Field(None, description="Rate limit per minute")
    is_available: bool = Field(..., description="Analyzer availability")
    last_sync: Optional[datetime] = Field(None, description="Last sync timestamp")
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, analyzer):
        """Convert CortexAnalyzer model to API response"""
        return cls(
            id=analyzer.uuid,
            name=analyzer.name,
            display_name=analyzer.display_name,
            version=analyzer.version,
            description=analyzer.description,
            data_types=analyzer.data_types,
            max_tlp=analyzer.max_tlp,
            max_pap=analyzer.max_pap,
            enabled=analyzer.enabled,
            configuration=analyzer.configuration,
            cortex_instance_id=analyzer.cortex_instance.uuid,
            cortex_instance_name=analyzer.cortex_instance.name,
            rate_limit=analyzer.rate_limit,
            is_available=analyzer.is_available,
            last_sync=analyzer.last_sync,
            created_at=analyzer.created_at,
            updated_at=analyzer.updated_at
        )

    class Config:
        from_attributes = True


class CortexResponderResponse(CortexWorkerBase):
    """Schema for Cortex responder response"""
    id: UUID4 = Field(..., description="Responder UUID")
    cortex_instance_id: UUID4 = Field(..., description="Cortex instance UUID")
    cortex_instance_name: str = Field(..., description="Cortex instance name")
    is_available: bool = Field(..., description="Responder availability")
    last_sync: Optional[datetime] = Field(None, description="Last sync timestamp")
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, responder):
        """Convert CortexResponder model to API response"""
        return cls(
            id=responder.uuid,
            name=responder.name,
            display_name=responder.display_name,
            version=responder.version,
            description=responder.description,
            data_types=responder.data_types,
            max_tlp=responder.max_tlp,
            max_pap=responder.max_pap,
            enabled=responder.enabled,
            configuration=responder.configuration,
            cortex_instance_id=responder.cortex_instance.uuid,
            cortex_instance_name=responder.cortex_instance.name,
            is_available=responder.is_available,
            last_sync=responder.last_sync,
            created_at=responder.created_at,
            updated_at=responder.updated_at
        )

    class Config:
        from_attributes = True


class CortexJobBase(BaseModel):
    """Base schema for Cortex job"""
    cortex_job_id: str = Field(..., description="Cortex job ID")
    worker_type: WorkerType = Field(..., description="Worker type")
    status: JobStatus = Field(JobStatus.WAITING, description="Job status")
    message: Optional[str] = Field(None, description="Job message")
    progress: int = Field(0, ge=0, le=100, description="Job progress percentage")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Job parameters")


class CortexJobCreate(CortexJobBase):
    """Schema for creating Cortex job"""
    observable_id: Optional[int] = Field(None, description="Observable ID")
    case_id: Optional[int] = Field(None, description="Case ID")


class CortexJobUpdate(BaseModel):
    """Schema for updating Cortex job"""
    status: Optional[JobStatus] = None
    message: Optional[str] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    report: Optional[Dict[str, Any]] = None
    artifacts: Optional[List[Dict[str, Any]]] = None


class CortexJobResponse(CortexJobBase):
    """Schema for Cortex job response"""
    id: UUID4 = Field(..., description="Job UUID")
    
    # Execution details
    started_at: Optional[datetime] = Field(None, description="Job start time")
    ended_at: Optional[datetime] = Field(None, description="Job end time")
    duration: Optional[float] = Field(None, description="Job duration in seconds")
    
    # Results
    report: Optional[Dict[str, Any]] = Field(None, description="Job report")
    artifacts: List[Dict[str, Any]] = Field(default_factory=list, description="Generated artifacts")
    
    # Relationships
    cortex_instance_id: UUID4 = Field(..., description="Cortex instance UUID")
    cortex_instance_name: str = Field(..., description="Cortex instance name")
    
    analyzer_id: Optional[UUID4] = Field(None, description="Analyzer UUID")
    analyzer_name: Optional[str] = Field(None, description="Analyzer name")
    
    responder_id: Optional[UUID4] = Field(None, description="Responder UUID")
    responder_name: Optional[str] = Field(None, description="Responder name")
    
    observable_id: Optional[UUID4] = Field(None, description="Observable UUID")
    case_id: Optional[UUID4] = Field(None, description="Case UUID")
    
    created_by_id: UUID4 = Field(..., description="Creator UUID")
    created_by_email: str = Field(..., description="Creator email")
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, job):
        """Convert CortexJob model to API response"""
        return cls(
            id=job.uuid,
            cortex_job_id=job.cortex_job_id,
            worker_type=job.worker_type,
            status=job.status,
            message=job.message,
            progress=job.progress,
            parameters=job.parameters,
            started_at=job.started_at,
            ended_at=job.ended_at,
            duration=job.duration,
            report=job.report,
            artifacts=job.artifacts,
            cortex_instance_id=job.cortex_instance.uuid,
            cortex_instance_name=job.cortex_instance.name,
            analyzer_id=job.analyzer.uuid if job.analyzer else None,
            analyzer_name=job.analyzer.name if job.analyzer else None,
            responder_id=job.responder.uuid if job.responder else None,
            responder_name=job.responder.name if job.responder else None,
            observable_id=job.observable.uuid if job.observable else None,
            case_id=job.case.uuid if job.case else None,
            created_by_id=job.created_by.uuid,
            created_by_email=job.created_by.email,
            created_at=job.created_at,
            updated_at=job.updated_at
        )

    class Config:
        from_attributes = True


class AnalysisRequest(BaseModel):
    """Schema for analysis request"""
    analyzer_id: UUID4 = Field(..., description="Analyzer UUID")
    observable_id: UUID4 = Field(..., description="Observable UUID")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Analysis parameters")


class ResponseRequest(BaseModel):
    """Schema for response request"""
    responder_id: UUID4 = Field(..., description="Responder UUID")
    object_type: str = Field(..., description="Object type (case, observable)")
    object_id: UUID4 = Field(..., description="Object UUID")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Response parameters")

    @validator('object_type')
    def validate_object_type(cls, v):
        """Validate object type"""
        allowed_types = ['case', 'observable']
        if v not in allowed_types:
            raise ValueError(f"Object type must be one of: {', '.join(allowed_types)}")
        return v


class SyncRequest(BaseModel):
    """Schema for sync request"""
    instance_id: UUID4 = Field(..., description="Cortex instance UUID")
    sync_analyzers: bool = Field(True, description="Sync analyzers")
    sync_responders: bool = Field(True, description="Sync responders")


class SyncResponse(BaseModel):
    """Schema for sync response"""
    instance_id: UUID4 = Field(..., description="Cortex instance UUID")
    analyzers_synced: int = Field(0, description="Number of analyzers synced")
    responders_synced: int = Field(0, description="Number of responders synced")
    errors: int = Field(0, description="Number of errors")
    duration: float = Field(..., description="Sync duration in seconds")


class CortexHealthCheck(BaseModel):
    """Schema for Cortex health check"""
    instance_id: UUID4 = Field(..., description="Cortex instance UUID")
    instance_name: str = Field(..., description="Cortex instance name")
    status: str = Field(..., description="Health status")
    version: Optional[str] = Field(None, description="Cortex version")
    response_time: float = Field(..., description="Response time in seconds")
    error: Optional[str] = Field(None, description="Error message if unhealthy")
    checked_at: datetime = Field(default_factory=datetime.utcnow, description="Check timestamp")