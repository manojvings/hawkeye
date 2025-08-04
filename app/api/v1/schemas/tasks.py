# app/api/v1/schemas/tasks.py
from pydantic import BaseModel, Field, UUID4, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskBase(BaseModel):
    """Base schema for task"""
    title: str = Field(..., min_length=1, max_length=500, description="Task title")
    description: Optional[str] = Field(None, description="Task description")
    due_date: Optional[datetime] = Field(None, description="Due date for the task")
    order_index: Optional[int] = Field(None, description="Order index within the case")


class TaskCreate(TaskBase):
    """Schema for creating a task"""
    assignee_email: Optional[str] = Field(None, description="Email of user to assign")


class TaskUpdate(BaseModel):
    """Schema for updating a task"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    due_date: Optional[datetime] = None
    order_index: Optional[int] = None
    assignee_email: Optional[str] = Field(None, description="Email of user to assign (null to unassign)")


class TaskResponse(TaskBase):
    """Schema for task response with UUID"""
    id: UUID4 = Field(..., description="Task UUID")
    status: TaskStatus = Field(..., description="Task status")
    case_id: UUID4 = Field(..., description="Case UUID")
    case_title: str = Field(..., description="Case title")
    case_number: str = Field(..., description="Case number")
    assignee_id: Optional[UUID4] = Field(None, description="Assignee UUID")
    assignee_email: Optional[str] = Field(None, description="Assignee email")
    created_by_id: UUID4 = Field(..., description="Creator UUID")
    created_by_email: str = Field(..., description="Creator email")
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    @classmethod
    def from_model(cls, task):
        """Convert Task model to API response using UUID"""
        return cls(
            id=task.uuid,
            title=task.title,
            description=task.description,
            status=task.status.value,
            due_date=task.due_date,
            order_index=task.order_index,
            case_id=task.case.uuid,
            case_title=task.case.title,
            case_number=task.case.case_number,
            assignee_id=task.assignee.uuid if task.assignee else None,
            assignee_email=task.assignee.email if task.assignee else None,
            created_by_id=task.created_by.uuid,
            created_by_email=task.created_by.email,
            created_at=task.created_at,
            updated_at=task.updated_at,
            completed_at=task.completed_at
        )

    class Config:
        from_attributes = True


class TaskSummary(BaseModel):
    """Lightweight task summary for lists"""
    id: UUID4
    title: str
    status: TaskStatus
    due_date: Optional[datetime]
    assignee_email: Optional[str]
    created_at: datetime
    updated_at: datetime
    order_index: int

    @classmethod
    def from_model(cls, task):
        """Convert Task model to summary"""
        return cls(
            id=task.uuid,
            title=task.title,
            status=task.status.value,
            due_date=task.due_date,
            assignee_email=task.assignee.email if task.assignee else None,
            created_at=task.created_at,
            updated_at=task.updated_at,
            order_index=task.order_index
        )

    class Config:
        from_attributes = True


class TaskStatusUpdate(BaseModel):
    """Schema for updating task status"""
    status: TaskStatus = Field(..., description="New task status")


class TaskReorderRequest(BaseModel):
    """Schema for reordering tasks"""
    task_orders: List[Dict[str, Any]] = Field(
        ..., 
        description="List of {task_uuid: UUID, order_index: int}"
    )

    @validator('task_orders')
    def validate_task_orders(cls, v):
        """Validate that each item has task_uuid and order_index"""
        for item in v:
            if 'task_uuid' not in item or 'order_index' not in item:
                raise ValueError("Each item must have 'task_uuid' and 'order_index'")
            if not isinstance(item['order_index'], int):
                raise ValueError("order_index must be an integer")
        return v


class BulkTaskStatusUpdate(BaseModel):
    """Schema for bulk status update"""
    task_ids: List[UUID4] = Field(..., description="List of task UUIDs to update")
    status: TaskStatus = Field(..., description="New status for all tasks")

    @validator('task_ids')
    def validate_task_ids(cls, v):
        """Ensure at least one task ID"""
        if not v:
            raise ValueError("At least one task ID is required")
        return v


class TaskStats(BaseModel):
    """Task statistics for a case"""
    total: int = Field(..., description="Total number of tasks")
    pending: int = Field(..., description="Number of pending tasks")
    in_progress: int = Field(..., description="Number of in-progress tasks")
    completed: int = Field(..., description="Number of completed tasks")

    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage"""
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100