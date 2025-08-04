# app/api/v1/endpoints/observables.py
"""Observable (IOC/Artifact) management endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query, status, Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from loguru import logger

from app.db.database import get_db
from app.db import crud
from app.db.models import User, Organization, ObservableType
from app.api.v1.schemas.observables import (
    ObservableCreate, ObservableUpdate, ObservableResponse, ObservableSummary,
    BulkObservableTagUpdate, BulkObservableIOCUpdate, ObservableStats,
    SimilarObservable, ObservableSearchRequest, ObservableEnrichmentResponse
)
from app.auth.dependencies import get_current_user, get_user_organization
from app.core.pagination import PaginationParams, PaginatedResponse

router = APIRouter()


@router.post("/", response_model=ObservableResponse, status_code=status.HTTP_201_CREATED)
async def create_observable(
    case_id: Optional[UUID] = Query(None, description="Case UUID to associate with"),
    observable_data: ObservableCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Create a new observable"""
    try:
        # Validate case if provided
        internal_case_id = None
        if case_id:
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
            internal_case_id = case.id

        # Create the observable
        observable = await crud.observable.create_observable(
            db=db,
            observable_data=observable_data,
            case_id=internal_case_id,
            creator_id=current_user.id
        )

        return ObservableResponse.from_model(observable)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create observable: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create observable"
        )


@router.get("/", response_model=PaginatedResponse[ObservableSummary])
async def list_organization_observables(
    pagination: PaginationParams = Depends(),
    data_type_filter: Optional[ObservableType] = Query(None, description="Filter by observable type"),
    is_ioc_filter: Optional[bool] = Query(None, description="Filter by IOC status"),
    search: Optional[str] = Query(None, description="Search in data, message, or source"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """List observables across the organization"""
    try:
        observables = await crud.observable.get_global_observables(
            db=db,
            organization_id=organization.id,
            skip=pagination.skip,
            limit=pagination.limit,
            data_type_filter=data_type_filter,
            is_ioc_filter=is_ioc_filter,
            search_term=search
        )

        # Convert to summary format
        observable_summaries = [ObservableSummary.from_model(obs) for obs in observables]

        return PaginatedResponse(
            items=observable_summaries,
            total=len(observable_summaries),  # TODO: Add proper count query
            page=pagination.page,
            per_page=pagination.limit,
            pages=(len(observable_summaries) + pagination.limit - 1) // pagination.limit
        )

    except Exception as e:
        logger.error(f"Failed to list observables: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve observables"
        )


@router.get("/case/{case_id}", response_model=PaginatedResponse[ObservableSummary])
async def list_case_observables(
    case_id: UUID = Path(..., description="Case UUID"),
    pagination: PaginationParams = Depends(),
    data_type_filter: Optional[ObservableType] = Query(None, description="Filter by observable type"),
    is_ioc_filter: Optional[bool] = Query(None, description="Filter by IOC status"),
    search: Optional[str] = Query(None, description="Search in data, message, or source"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """List observables for a specific case"""
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

        # Get observables with filters
        observables = await crud.observable.get_case_observables(
            db=db,
            case_id=case.id,
            skip=pagination.skip,
            limit=pagination.limit,
            data_type_filter=data_type_filter,
            is_ioc_filter=is_ioc_filter,
            search_term=search
        )

        # Convert to summary format
        observable_summaries = [ObservableSummary.from_model(obs) for obs in observables]

        return PaginatedResponse(
            items=observable_summaries,
            total=len(observable_summaries),
            page=pagination.page,
            per_page=pagination.limit,
            pages=(len(observable_summaries) + pagination.limit - 1) // pagination.limit
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list case observables: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve observables"
        )


@router.get("/{observable_id}", response_model=ObservableResponse)
async def get_observable(
    observable_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Get a specific observable by UUID"""
    try:
        observable = await crud.observable.get_observable_by_uuid(db, observable_id)
        if not observable:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Observable not found"
            )

        # Check organization access through case (if observable has a case)
        if observable.case and observable.case.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this observable"
            )

        return ObservableResponse.from_model(observable)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get observable {observable_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve observable"
        )


@router.put("/{observable_id}", response_model=ObservableResponse)
async def update_observable(
    observable_id: UUID,
    updates: ObservableUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Update an observable"""
    try:
        observable = await crud.observable.get_observable_by_uuid(db, observable_id)
        if not observable:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Observable not found"
            )

        # Check organization access through case (if observable has a case)
        if observable.case and observable.case.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this observable"
            )

        # Update the observable
        updated_observable = await crud.observable.update_observable(
            db=db,
            observable=observable,
            updates=updates,
            editor_id=current_user.id
        )

        return ObservableResponse.from_model(updated_observable)

    except HTTPException:
        raise  
    except Exception as e:
        logger.error(f"Failed to update observable {observable_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update observable"
        )


@router.delete("/{observable_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_observable(
    observable_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Delete an observable"""
    try:
        observable = await crud.observable.get_observable_by_uuid(db, observable_id)
        if not observable:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Observable not found"
            )

        # Check organization access through case (if observable has a case)
        if observable.case and observable.case.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this observable"
            )

        # Delete the observable
        success = await crud.observable.delete_observable(db, observable)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete observable"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete observable {observable_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete observable"
        )


@router.post("/{observable_id}/sight", response_model=ObservableResponse)
async def sight_observable(
    observable_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Increment the sighted count for an observable"""
    try:
        observable = await crud.observable.get_observable_by_uuid(db, observable_id)
        if not observable:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Observable not found"
            )

        # Check organization access through case (if observable has a case)
        if observable.case and observable.case.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this observable"
            )

        # Increment sighted count
        updated_observable = await crud.observable.increment_sighted_count(db, observable)
        return ObservableResponse.from_model(updated_observable)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to sight observable {observable_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to sight observable"
        )


@router.get("/{observable_id}/similar", response_model=List[SimilarObservable])
async def get_similar_observables(
    observable_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Get similar observables for enrichment"""
    try:
        observable = await crud.observable.get_observable_by_uuid(db, observable_id)
        if not observable:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Observable not found"
            )

        # Check organization access through case (if observable has a case)
        if observable.case and observable.case.organization_id != organization.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this observable"
            )

        # Find similar observables
        similar_observables = await crud.observable.find_similar_observables(
            db=db,
            data=observable.data,
            data_type=observable.data_type,
            organization_id=organization.id,
            exclude_observable_id=observable.id
        )

        return [SimilarObservable.from_model(obs) for obs in similar_observables]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get similar observables for {observable_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve similar observables"
        )


@router.post("/search", response_model=List[ObservableResponse])
async def search_observables(
    search_request: ObservableSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Search observables by data value"""
    try:
        observables = await crud.observable.search_observables_by_data(
            db=db,
            search_data=search_request.search_term,
            organization_id=organization.id,
            exact_match=search_request.exact_match
        )

        # Apply additional filters if provided
        if search_request.data_type_filter:
            observables = [obs for obs in observables if obs.data_type == search_request.data_type_filter]

        if search_request.is_ioc_filter is not None:
            observables = [obs for obs in observables if obs.is_ioc == search_request.is_ioc_filter]

        return [ObservableResponse.from_model(obs) for obs in observables]

    except Exception as e:
        logger.error(f"Failed to search observables: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search observables"
        )


@router.post("/case/{case_id}/bulk-tags", response_model=dict)
async def bulk_update_observable_tags(
    case_id: UUID,
    bulk_update: BulkObservableTagUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Bulk update tags for multiple observables"""
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

        # Bulk update tags
        updated_count = await crud.observable.bulk_update_observable_tags(
            db=db,
            observable_uuids=bulk_update.observable_ids,
            tags=bulk_update.tags,
            case_id=case.id
        )

        return {
            "message": f"Updated tags for {updated_count} observables",
            "updated_count": updated_count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to bulk update observable tags: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to bulk update observable tags"
        )


@router.post("/case/{case_id}/bulk-ioc", response_model=dict)
async def bulk_update_observable_ioc_status(
    case_id: UUID,
    bulk_update: BulkObservableIOCUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Bulk mark observables as IOC or artifact"""
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

        # Bulk update IOC status
        updated_count = await crud.observable.bulk_mark_as_ioc(
            db=db,
            observable_uuids=bulk_update.observable_ids,
            case_id=case.id,
            is_ioc=bulk_update.is_ioc
        )

        return {
            "message": f"Marked {updated_count} observables as {'IOC' if bulk_update.is_ioc else 'artifact'}",
            "updated_count": updated_count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to bulk update IOC status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to bulk update IOC status"
        )


@router.get("/case/{case_id}/stats", response_model=ObservableStats)
async def get_case_observable_stats(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization)
):
    """Get observable statistics for a case"""
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
        stats = await crud.observable.get_ioc_stats_by_case(db, case.id)
        return ObservableStats(**stats)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get observable stats for case {case_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve observable statistics"
        )