# app/api/v1/endpoints/alerts.py
"""Alert management endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query, status, Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from loguru import logger

from app.db.database import get_db
from app.db import crud
from app.db.models import User, Organization, AlertStatus, Severity
from app.api.v1.schemas.alerts import (
    AlertCreate, AlertUpdate, AlertResponse, AlertSummary,
    AlertPromotionRequest, BulkAlertStatusUpdate, AlertAcknowledgmentRequest,
    AlertIgnoreRequest, AlertStats, AlertSearchRequest, AlertImportResult
)
from app.api.v1.schemas.cases import CaseResponse
from app.auth.dependencies import get_current_user, get_user_organization
from app.core.pagination import PaginationParams, PaginatedResponse

router = APIRouter()


@router.post("/", response_model=AlertImportResult, status_code=status.HTTP_201_CREATED)
async def create_alert(
    alert_data: AlertCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Create a new alert (usually from external systems)"""
    try:
        # Check if alert already exists
        existing_alert = await crud.alert.get_alert_by_source_ref(
            db, alert_data.source, alert_data.source_ref
        )
        
        if existing_alert:
            return AlertImportResult(
                success=True,
                alert_id=existing_alert.uuid,
                message=f"Alert already exists from {alert_data.source}",
                duplicate=True,
                existing_alert_id=existing_alert.uuid
            )

        # Create the alert
        alert = await crud.alert.create_alert(
            db=db,
            alert_data=alert_data,
            organization_id=organization.id,
            creator_id=current_user.id
        )

        return AlertImportResult(
            success=True,
            alert_id=alert.uuid,
            message=f"Alert created successfully from {alert_data.source}",
            duplicate=False
        )

    except ValueError as e:
        return AlertImportResult(
            success=False,
            message=str(e),
            duplicate=True
        )
    except Exception as e:
        logger.error(f"Failed to create alert: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create alert"
        )


@router.get("/", response_model=PaginatedResponse[AlertSummary])
async def list_alerts(
    pagination: PaginationParams = Depends(),
    status_filter: Optional[AlertStatus] = Query(None, description="Filter by alert status"),
    severity_filter: Optional[Severity] = Query(None, description="Filter by severity"),
    source_filter: Optional[str] = Query(None, description="Filter by source system"),
    search: Optional[str] = Query(None, description="Search in title, description, or source"),
    include_imported: bool = Query(True, description="Include imported alerts"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """List alerts in the organization"""
    try:
        alerts = await crud.alert.get_organization_alerts(
            db=db,
            organization_id=organization.id,
            skip=pagination.skip,
            limit=pagination.limit,
            status_filter=status_filter,
            severity_filter=severity_filter,
            source_filter=source_filter,
            search_term=search,
            include_imported=include_imported
        )

        # Convert to summary format
        alert_summaries = [AlertSummary.from_model(alert) for alert in alerts]

        return PaginatedResponse(
            items=alert_summaries,
            total=len(alert_summaries),  # TODO: Add proper count query
            page=pagination.page,
            per_page=pagination.limit,
            pages=(len(alert_summaries) + pagination.limit - 1) // pagination.limit
        )

    except Exception as e:
        logger.error(f"Failed to list alerts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve alerts"
        )


@router.get("/source/{source_name}", response_model=PaginatedResponse[AlertSummary])
async def list_alerts_by_source(
    source_name: str = Path(..., description="Source system name"),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """List alerts from a specific source system"""
    try:
        alerts = await crud.alert.get_alerts_by_source(
            db=db,
            organization_id=organization.id,
            source=source_name,
            skip=pagination.skip,
            limit=pagination.limit
        )

        alert_summaries = [AlertSummary.from_model(alert) for alert in alerts]

        return PaginatedResponse(
            items=alert_summaries,
            total=len(alert_summaries),
            page=pagination.page,
            per_page=pagination.limit,
            pages=(len(alert_summaries) + pagination.limit - 1) // pagination.limit
        )

    except Exception as e:
        logger.error(f"Failed to list alerts by source {source_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve alerts"
        )


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Get a specific alert by UUID"""
    try:
        alert = await crud.alert.get_alert_by_uuid(db, alert_id)
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert not found"
            )

        # Check organization access
        if alert.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this alert"
            )

        return AlertResponse.from_model(alert)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get alert {alert_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve alert"
        )


@router.put("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: UUID,
    updates: AlertUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Update an alert"""
    try:
        alert = await crud.alert.get_alert_by_uuid(db, alert_id)
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert not found"
            )

        # Check organization access
        if alert.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this alert"
            )

        # Update the alert
        updated_alert = await crud.alert.update_alert(
            db=db,
            alert=alert,
            updates=updates,
            editor_id=current_user.id
        )

        return AlertResponse.from_model(updated_alert)

    except HTTPException:
        raise  
    except Exception as e:
        logger.error(f"Failed to update alert {alert_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update alert"
        )


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Delete an alert"""
    try:
        alert = await crud.alert.get_alert_by_uuid(db, alert_id)
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert not found"
            )

        # Check organization access
        if alert.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this alert"
            )

        # Don't allow deletion of imported alerts
        if alert.case_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete alert that has been imported to a case"
            )

        # Delete the alert
        success = await crud.alert.delete_alert(db, alert)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete alert"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete alert {alert_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete alert"
        )


@router.post("/{alert_id}/promote", response_model=CaseResponse)
async def promote_alert_to_case(
    alert_id: UUID,
    promotion_request: AlertPromotionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Promote an alert to a case"""
    try:
        alert = await crud.alert.get_alert_by_uuid(db, alert_id)
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert not found"
            )

        # Check organization access
        if alert.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this alert"
            )

        # Check if already imported
        if alert.case_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Alert has already been imported to a case"
            )

        # Handle assignee by email if provided
        assignee_id = None
        if promotion_request.assignee_email:
            assignee = await crud.user.get_user_by_email(db, promotion_request.assignee_email)
            if not assignee:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User with email {promotion_request.assignee_email} not found"
                )
            # Check if assignee is in the same organization
            if not await crud.user.is_user_in_organization(db, assignee.id, organization.id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Assignee must be in the same organization"
                )
            assignee_id = assignee.id

        # Promote alert to case
        case = await crud.alert.promote_alert_to_case(
            db=db,
            alert=alert,
            case_title=promotion_request.case_title,
            case_description=promotion_request.case_description,
            assignee_id=assignee_id,
            creator_id=current_user.id
        )

        # Get case statistics for response
        stats = await crud.case.get_case_stats(db, case.id)

        from app.api.v1.schemas.cases import CaseResponse
        return CaseResponse.from_model(
            case,
            task_count=stats["task_count"],
            observable_count=stats["observable_count"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to promote alert {alert_id} to case: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to promote alert to case"
        )


@router.post("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: UUID,
    ack_request: AlertAcknowledgmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Acknowledge an alert"""
    try:
        alert = await crud.alert.get_alert_by_uuid(db, alert_id)
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert not found"
            )

        # Check organization access
        if alert.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this alert"
            )

        # Acknowledge the alert
        acknowledged_alert = await crud.alert.acknowledge_alert(
            db=db,
            alert=alert,
            user_id=current_user.id
        )

        # Add notes if provided
        if ack_request.notes:
            if not acknowledged_alert.raw_data:
                acknowledged_alert.raw_data = {}
            acknowledged_alert.raw_data["acknowledgment_notes"] = ack_request.notes
            await db.commit()
            await db.refresh(acknowledged_alert)

        return AlertResponse.from_model(acknowledged_alert)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to acknowledge alert {alert_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to acknowledge alert"
        )


@router.post("/{alert_id}/ignore", response_model=AlertResponse)
async def ignore_alert(
    alert_id: UUID,
    ignore_request: AlertIgnoreRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Ignore an alert"""
    try:
        alert = await crud.alert.get_alert_by_uuid(db, alert_id)
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert not found"
            )

        # Check organization access
        if alert.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this alert"
            )

        # Ignore the alert
        ignored_alert = await crud.alert.ignore_alert(
            db=db,
            alert=alert,
            user_id=current_user.id,
            reason=ignore_request.reason
        )

        return AlertResponse.from_model(ignored_alert)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to ignore alert {alert_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to ignore alert"
        )


@router.post("/bulk-status", response_model=dict)
async def bulk_update_alert_status(
    bulk_update: BulkAlertStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Bulk update alert status for multiple alerts"""
    try:
        # Bulk update alerts
        updated_count = await crud.alert.bulk_update_alert_status(
            db=db,
            alert_uuids=bulk_update.alert_ids,
            new_status=bulk_update.status,
            organization_id=organization.id
        )

        return {
            "message": f"Updated {updated_count} alerts to status {bulk_update.status.value}",
            "updated_count": updated_count
        }

    except Exception as e:
        logger.error(f"Failed to bulk update alert status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to bulk update alert status"
        )


@router.get("/stats/organization", response_model=AlertStats)
async def get_organization_alert_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Get alert statistics for the organization"""
    try:
        stats = await crud.alert.get_alert_stats_by_organization(db, organization.id)
        return AlertStats(**stats)

    except Exception as e:
        logger.error(f"Failed to get alert stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve alert statistics"
        )