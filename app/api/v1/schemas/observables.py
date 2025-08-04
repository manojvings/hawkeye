# app/api/v1/schemas/observables.py
from pydantic import BaseModel, Field, UUID4, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ObservableType(str, Enum):
    """Observable data types"""
    DOMAIN = "domain"
    URL = "url"
    IP = "ip"
    HASH_MD5 = "hash_md5"
    HASH_SHA1 = "hash_sha1"
    HASH_SHA256 = "hash_sha256"
    EMAIL = "email"
    FILENAME = "filename"
    FILEPATH = "filepath"
    REGISTRY_KEY = "registry_key" 
    USER_AGENT = "user_agent"
    AUTONOMOUS_SYSTEM = "autonomous_system"
    OTHER = "other"


class TLP(str, Enum):
    """Traffic Light Protocol levels"""
    WHITE = "white"
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class ObservableBase(BaseModel):
    """Base schema for observable"""
    data_type: ObservableType = Field(..., description="Type of observable data")
    data: str = Field(..., min_length=1, max_length=1000, description="Observable data value")
    tlp: TLP = Field(TLP.AMBER, description="Traffic Light Protocol level")
    is_ioc: bool = Field(False, description="Whether this is an Indicator of Compromise")
    tags: Optional[List[str]] = Field(default_factory=list, description="Observable tags")
    source: Optional[str] = Field(None, max_length=255, description="Source of the observable")
    message: Optional[str] = Field(None, description="Additional message or context")
    sighted: bool = Field(False, description="Has been observed in environment")
    ignore_similarity: Optional[bool] = Field(None, description="Skip similarity detection")

    @validator('data')
    def validate_data(cls, v):
        """Validate and clean data"""
        return v.strip()

    @validator('tags')
    def validate_tags(cls, v):
        """Validate tags"""
        if v is None:
            return []
        # Remove duplicates and empty tags
        return list(set(tag.strip() for tag in v if tag.strip()))


class ObservableCreate(ObservableBase):
    """Schema for creating an observable"""
    pass


class ObservableUpdate(BaseModel):
    """Schema for updating an observable"""
    data_type: Optional[ObservableType] = None
    data: Optional[str] = Field(None, min_length=1, max_length=1000)
    tlp: Optional[TLP] = None
    is_ioc: Optional[bool] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = Field(None, max_length=255)
    message: Optional[str] = None
    sighted: Optional[bool] = None
    ignore_similarity: Optional[bool] = None

    @validator('data')
    def validate_data(cls, v):
        """Validate and clean data"""
        if v is not None:
            return v.strip()
        return v

    @validator('tags')
    def validate_tags(cls, v):
        """Validate tags"""
        if v is None:
            return v
        # Remove duplicates and empty tags
        return list(set(tag.strip() for tag in v if tag.strip()))


class ObservableResponse(ObservableBase):
    """Schema for observable response with UUID"""
    id: UUID4 = Field(..., description="Observable UUID")
    case_id: Optional[UUID4] = Field(None, description="Case UUID if associated")
    case_title: Optional[str] = Field(None, description="Case title if associated")
    case_number: Optional[str] = Field(None, description="Case number if associated")
    created_by_id: UUID4 = Field(..., description="Creator UUID")
    created_by_email: str = Field(..., description="Creator email")
    sighted_count: int = Field(0, description="Number of times this observable was sighted")
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, observable):
        """Convert Observable model to API response using UUID"""
        return cls(
            id=observable.uuid,
            data_type=observable.data_type.value,
            data=observable.data,
            tlp=observable.tlp.value,
            is_ioc=observable.is_ioc,
            tags=observable.tags or [],
            source=observable.source,
            message=observable.message,
            sighted=observable.sighted,
            ignore_similarity=observable.ignore_similarity,
            case_id=observable.case.uuid if observable.case else None,
            case_title=observable.case.title if observable.case else None,
            case_number=observable.case.case_number if observable.case else None,
            created_by_id=observable.created_by.uuid,
            created_by_email=observable.created_by.email,
            sighted_count=observable.sighted_count,
            created_at=observable.created_at,
            updated_at=observable.updated_at
        )

    class Config:
        from_attributes = True


class ObservableSummary(BaseModel):
    """Lightweight observable summary for lists"""
    id: UUID4
    data_type: ObservableType
    data: str
    is_ioc: bool
    tags: List[str]
    sighted_count: int
    created_at: datetime

    @classmethod
    def from_model(cls, observable):
        """Convert Observable model to summary"""
        return cls(
            id=observable.uuid,
            data_type=observable.data_type.value,
            data=observable.data,
            is_ioc=observable.is_ioc,
            tags=observable.tags or [],
            sighted_count=observable.sighted_count,
            created_at=observable.created_at
        )

    class Config:
        from_attributes = True


class BulkObservableTagUpdate(BaseModel):
    """Schema for bulk tag update"""
    observable_ids: List[UUID4] = Field(..., description="List of observable UUIDs to update")
    tags: List[str] = Field(..., description="Tags to add to all observables")

    @validator('observable_ids') 
    def validate_observable_ids(cls, v):
        """Ensure at least one observable ID"""
        if not v:
            raise ValueError("At least one observable ID is required")
        return v

    @validator('tags')
    def validate_tags(cls, v):
        """Validate and clean tags"""
        if not v:
            raise ValueError("At least one tag is required")
        # Remove duplicates and empty tags
        return list(set(tag.strip() for tag in v if tag.strip()))


class BulkObservableIOCUpdate(BaseModel):
    """Schema for bulk IOC status update"""
    observable_ids: List[UUID4] = Field(..., description="List of observable UUIDs to update")
    is_ioc: bool = Field(..., description="Whether to mark as IOC or artifact")

    @validator('observable_ids')
    def validate_observable_ids(cls, v):
        """Ensure at least one observable ID"""
        if not v:
            raise ValueError("At least one observable ID is required")
        return v


class ObservableStats(BaseModel):
    """Observable statistics for a case"""
    total: int = Field(..., description="Total number of observables")
    ioc: int = Field(..., description="Number of IOCs")
    artifacts: int = Field(..., description="Number of artifacts")
    by_type: Dict[str, int] = Field(..., description="Count by observable type")

    @property
    def ioc_percentage(self) -> float:
        """Calculate IOC percentage"""
        if self.total == 0:
            return 0.0
        return (self.ioc / self.total) * 100


class SimilarObservable(BaseModel):
    """Similar observable for enrichment"""
    id: UUID4
    data: str
    case_id: UUID4
    case_title: str
    case_number: str
    is_ioc: bool
    sighted_count: int
    created_at: datetime

    @classmethod
    def from_model(cls, observable):
        """Convert Observable model to similar observable"""
        return cls(
            id=observable.uuid,
            data=observable.data,
            case_id=observable.case.uuid,
            case_title=observable.case.title,
            case_number=observable.case.case_number,
            is_ioc=observable.is_ioc,
            sighted_count=observable.sighted_count,
            created_at=observable.created_at
        )

    class Config:
        from_attributes = True


class ObservableSearchRequest(BaseModel):
    """Schema for observable search"""
    search_term: str = Field(..., min_length=1, description="Search term")
    exact_match: bool = Field(False, description="Whether to perform exact match")
    data_type_filter: Optional[ObservableType] = Field(None, description="Filter by data type")
    is_ioc_filter: Optional[bool] = Field(None, description="Filter by IOC status")


class ObservableEnrichmentResponse(BaseModel):
    """Observable enrichment data"""
    observable: ObservableResponse
    similar_observables: List[SimilarObservable] = Field(default_factory=list)
    related_cases: List[str] = Field(default_factory=list, description="Related case numbers")
    first_seen: datetime = Field(..., description="First time this observable was seen")
    last_seen: datetime = Field(..., description="Last time this observable was seen")
    total_sightings: int = Field(0, description="Total sightings across all cases")