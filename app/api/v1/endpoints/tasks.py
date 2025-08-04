# app/api/v1/endpoints/tasks.py
"""Task management endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query, status, Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from loguru import logger

from app.db.database import get_db
from app.db import crud
from app.db.models import User, Organization, TaskStatus
from app.api.v1.schemas.tasks import (
    TaskCreate, TaskUpdate, TaskResponse, TaskSummary, TaskStatusUpdate,
    TaskReorderRequest, BulkTaskStatusUpdate, TaskStats
)
from app.auth.dependencies import get_current_user, get_user_organization
from app.core.pagination import PaginationParams, PaginatedResponse

router = APIRouter()


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    case_id: UUID = Path(..., description="Case UUID"),
    task_data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Create a new task for a case"""
    try:
        # Get the case and verify access
        case = await crud.case.get_case_by_uuid(db, case_id)
        if not case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found"
            )

        # Check organization access
        if case.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this case"
            )

        # Handle assignee by email if provided
        assignee_id = None
        if task_data.assignee_email:
            assignee = await crud.user.get_user_by_email(db, task_data.assignee_email)
            if not assignee:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User with email {task_data.assignee_email} not found"
                )
            # Check if assignee is in the same organization
            if not await crud.user.is_user_in_organization(db, assignee.id, organization.id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Assignee must be in the same organization"
                )
            assignee_id = assignee.id

        # Create the task
        task = await crud.task.create_task(
            db=db,
            task_data=task_data,
            case_id=case.id,
            creator_id=current_user.id,
            assignee_id=assignee_id
        )

        return TaskResponse.from_model(task)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create task"
        )


@router.get("/case/{case_id}", response_model=PaginatedResponse[TaskSummary])
async def list_case_tasks(
    case_id: UUID = Path(..., description="Case UUID"),
    pagination: PaginationParams = Depends(),
    status_filter: Optional[TaskStatus] = Query(None, description="Filter by task status"),
    assignee_email: Optional[str] = Query(None, description="Filter by assignee email"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """List tasks for a specific case"""
    try:
        # Get the case and verify access
        case = await crud.case.get_case_by_uuid(db, case_id)
        if not case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found"
            )

        # Check organization access
        if case.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this case"
            )

        # Handle assignee filter
        assignee_id = None
        if assignee_email is not None:
            if assignee_email == "":  # Empty string means unassigned
                assignee_id = 0
            else:
                assignee = await crud.user.get_user_by_email(db, assignee_email)
                if not assignee:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"User with email {assignee_email} not found"
                    )
                assignee_id = assignee.id

        # Get tasks with filters
        tasks = await crud.task.get_case_tasks(
            db=db,
            case_id=case.id,
            skip=pagination.skip,
            limit=pagination.limit,
            status_filter=status_filter,
            assignee_id=assignee_id
        )

        # Convert to summary format
        task_summaries = [TaskSummary.from_model(task) for task in tasks]

        return PaginatedResponse(
            items=task_summaries,
            total=len(task_summaries),  # TODO: Add proper count query
            page=pagination.page,
            per_page=pagination.limit,
            pages=(len(task_summaries) + pagination.limit - 1) // pagination.limit
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list case tasks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve tasks"
        )


@router.get("/my-assignments", response_model=PaginatedResponse[TaskResponse])
async def list_my_assigned_tasks(
    pagination: PaginationParams = Depends(),
    status_filter: Optional[TaskStatus] = Query(None, description="Filter by task status"),
    case_id: Optional[UUID] = Query(None, description="Filter by case UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """List tasks assigned to the current user"""
    try:
        # Convert case UUID to ID if provided
        internal_case_id = None
        if case_id:
            case = await crud.case.get_case_by_uuid(db, case_id)
            if not case or case.organization_id != organization.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Case not found"
                )
            internal_case_id = case.id

        tasks = await crud.task.get_user_assigned_tasks(
            db=db,
            user_id=current_user.id,
            case_id=internal_case_id,
            status_filter=status_filter,
            skip=pagination.skip,
            limit=pagination.limit
        )

        # Filter by organization
        org_tasks = [task for task in tasks if task.case.organization_id == organization.id]
        task_responses = [TaskResponse.from_model(task) for task in org_tasks]

        return PaginatedResponse(
            items=task_responses,
            total=len(task_responses),
            page=pagination.page,
            per_page=pagination.limit,
            pages=(len(task_responses) + pagination.limit - 1) // pagination.limit
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list assigned tasks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve assigned tasks"
        )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Get a specific task by UUID"""
    try:
        task = await crud.task.get_task_by_uuid(db, task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )

        # Check organization access through case
        if task.case.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this task"
            )

        return TaskResponse.from_model(task)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task {task_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve task"
        )


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    updates: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Update a task"""
    try:
        task = await crud.task.get_task_by_uuid(db, task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )

        # Check organization access through case
        if task.case.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this task"
            )

        # Update the task
        updated_task = await crud.task.update_task(
            db=db,
            task=task,
            updates=updates,
            editor_id=current_user.id
        )

        return TaskResponse.from_model(updated_task)

    except HTTPException:
        raise  
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to update task {task_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update task"
        )


@router.patch("/{task_id}/status", response_model=TaskResponse)
async def update_task_status(
    task_id: UUID,
    status_update: TaskStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Update task status"""
    try:
        task = await crud.task.get_task_by_uuid(db, task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )

        # Check organization access through case
        if task.case.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this task"
            )

        # Create update with status
        updates = TaskUpdate(status=status_update.status)

        # Update the task
        updated_task = await crud.task.update_task(
            db=db,
            task=task,
            updates=updates,
            editor_id=current_user.id
        )

        return TaskResponse.from_model(updated_task)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update task status {task_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update task status"
        )


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Delete a task"""
    try:
        task = await crud.task.get_task_by_uuid(db, task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )

        # Check organization access through case
        if task.case.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this task"
            )

        # Delete the task
        success = await crud.task.delete_task(db, task)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete task"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete task {task_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete task"
        )


@router.post("/case/{case_id}/reorder", status_code=status.HTTP_200_OK)
async def reorder_case_tasks(
    case_id: UUID,
    reorder_request: TaskReorderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Reorder tasks within a case"""
    try:
        # Get the case and verify access
        case = await crud.case.get_case_by_uuid(db, case_id)
        if not case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found"
            )

        # Check organization access
        if case.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this case"
            )

        # Reorder tasks
        success = await crud.task.reorder_tasks(
            db=db,
            case_id=case.id,
            task_orders=reorder_request.task_orders
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reorder tasks"
            )

        return {"message": "Tasks reordered successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reorder tasks for case {case_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reorder tasks"
        )


@router.post("/case/{case_id}/bulk-status", response_model=dict)
async def bulk_update_task_status(
    case_id: UUID,
    bulk_update: BulkTaskStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Bulk update task status for multiple tasks"""
    try:
        # Get the case and verify access
        case = await crud.case.get_case_by_uuid(db, case_id)
        if not case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found"
            )

        # Check organization access
        if case.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this case"
            )

        # Bulk update tasks
        updated_count = await crud.task.bulk_update_task_status(
            db=db,
            task_uuids=bulk_update.task_ids,
            new_status=bulk_update.status,
            case_id=case.id
        )

        return {
            "message": f"Updated {updated_count} tasks to status {bulk_update.status.value}",
            "updated_count": updated_count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to bulk update task status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to bulk update task status"
        )


@router.get("/case/{case_id}/stats", response_model=TaskStats)
async def get_case_task_stats(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Get task statistics for a case"""
    try:
        # Get the case and verify access
        case = await crud.case.get_case_by_uuid(db, case_id)
        if not case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found"
            )

        # Check organization access
        if case.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this case"
            )

        # Get statistics
        stats = await crud.task.get_task_stats_by_case(db, case.id)
        return TaskStats(**stats)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task stats for case {case_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve task statistics"
        )