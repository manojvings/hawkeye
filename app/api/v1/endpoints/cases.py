# app/api/v1/endpoints/cases.py
"""Case management endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from loguru import logger

from app.db.database import get_db
from app.db import crud
from app.db.models import User, Organization, CaseStatus, Severity
from app.api.v1.schemas.cases import (
    CaseCreate, CaseUpdate, CaseResponse, CaseSummary, CaseStatusUpdate
)
from app.auth.dependencies import get_current_user, get_user_organization
from app.core.pagination import PaginationParams, PaginatedResponse

router = APIRouter()


@router.post("/", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    case_data: CaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Create a new case"""
    try:
        # Handle assignee by email if provided
        assignee_id = None
        if case_data.assignee_email:
            assignee = await crud.user.get_user_by_email(db, case_data.assignee_email)
            if not assignee:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User with email {case_data.assignee_email} not found"
                )
            # Check if assignee is in the same organization
            if not await crud.user.is_user_in_organization(db, assignee.id, organization.id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Assignee must be in the same organization"
                )
            assignee_id = assignee.id

        # Create the case
        case = await crud.case.create_case(
            db=db,
            case_data=case_data,
            organization_id=organization.id,
            creator_id=current_user.id,
            assignee_id=assignee_id
        )

        # Get case statistics
        stats = await crud.case.get_case_stats(db, case.id)

        return CaseResponse.from_model(
            case, 
            task_count=stats["task_count"],
            observable_count=stats["observable_count"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create case: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create case"
        )


@router.get("/", response_model=PaginatedResponse[CaseSummary])
async def list_cases(
    pagination: PaginationParams = Depends(),
    status_filter: Optional[CaseStatus] = Query(None, description="Filter by case status"),
    severity_filter: Optional[Severity] = Query(None, description="Filter by severity"),
    assignee_email: Optional[str] = Query(None, description="Filter by assignee email"),
    search: Optional[str] = Query(None, description="Search in title, description, or case number"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """List cases in the organization"""
    try:
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

        # Get cases with filters
        cases = await crud.case.get_organization_cases(
            db=db,
            organization_id=organization.id,
            skip=pagination.skip,
            limit=pagination.limit,
            status_filter=status_filter,
            assignee_id=assignee_id,
            severity_filter=severity_filter,
            search_term=search
        )

        # Convert to summary format
        case_summaries = [CaseSummary.from_model(case) for case in cases]

        return PaginatedResponse(
            items=case_summaries,
            total=len(case_summaries),  # TODO: Add proper count query
            page=pagination.page,
            per_page=pagination.limit,
            pages=(len(case_summaries) + pagination.limit - 1) // pagination.limit
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list cases: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve cases"
        )


@router.get("/my-assignments", response_model=PaginatedResponse[CaseSummary])
async def list_my_assigned_cases(
    pagination: PaginationParams = Depends(),
    status_filter: Optional[CaseStatus] = Query(None, description="Filter by case status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """List cases assigned to the current user"""
    try:
        cases = await crud.case.get_user_assigned_cases(
            db=db,
            user_id=current_user.id,
            organization_id=organization.id,
            status_filter=status_filter,
            skip=pagination.skip,
            limit=pagination.limit
        )

        case_summaries = [CaseSummary.from_model(case) for case in cases]

        return PaginatedResponse(
            items=case_summaries,
            total=len(case_summaries),
            page=pagination.page,
            per_page=pagination.limit,
            pages=(len(case_summaries) + pagination.limit - 1) // pagination.limit
        )

    except Exception as e:
        logger.error(f"Failed to list assigned cases: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve assigned cases"
        )


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Get a specific case by UUID"""
    try:
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

        # Get case statistics
        stats = await crud.case.get_case_stats(db, case.id)

        return CaseResponse.from_model(
            case,
            task_count=stats["task_count"],
            observable_count=stats["observable_count"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get case {case_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve case"
        )


@router.put("/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: UUID,
    updates: CaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Update a case"""
    try:
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

        # Update the case
        updated_case = await crud.case.update_case(
            db=db,
            case=case,
            updates=updates,
            editor_id=current_user.id
        )

        # Get case statistics
        stats = await crud.case.get_case_stats(db, updated_case.id)

        return CaseResponse.from_model(
            updated_case,
            task_count=stats["task_count"],
            observable_count=stats["observable_count"]
        )

    except HTTPException:
        raise  
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to update case {case_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update case"
        )


@router.patch("/{case_id}/status", response_model=CaseResponse)
async def update_case_status(
    case_id: UUID,
    status_update: CaseStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Update case status with validation"""
    try:
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

        # Create update with status and optional notes
        updates = CaseUpdate(status=status_update.status)
        if status_update.resolution_notes:
            # Add resolution notes to custom fields
            custom_fields = case.custom_fields or {}
            custom_fields["resolution_notes"] = status_update.resolution_notes
            updates.custom_fields = custom_fields

        # Update the case
        updated_case = await crud.case.update_case(
            db=db,
            case=case,
            updates=updates,
            editor_id=current_user.id
        )

        # Get case statistics
        stats = await crud.case.get_case_stats(db, updated_case.id)

        return CaseResponse.from_model(
            updated_case,
            task_count=stats["task_count"],
            observable_count=stats["observable_count"]
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to update case status {case_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update case status"
        )


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Delete a case (soft delete by closing)"""
    try:
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

        # Soft delete by closing the case
        success = await crud.case.delete_case(db, case)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete case"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete case {case_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete case"
        )


@router.get("/number/{case_number}", response_model=CaseResponse)
async def get_case_by_number(
    case_number: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Get a case by case number"""
    try:
        case = await crud.case.get_case_by_number(db, case_number)
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

        # Get case statistics
        stats = await crud.case.get_case_stats(db, case.id)

        return CaseResponse.from_model(
            case,
            task_count=stats["task_count"],
            observable_count=stats["observable_count"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get case by number {case_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve case"
        )