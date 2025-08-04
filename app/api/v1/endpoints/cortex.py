# app/api/v1/endpoints/cortex.py
"""Cortex integration API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
import time
from datetime import datetime

from app.db.database import get_db
from app.db.crud.cortex import (
    get_cortex_instance_by_uuid,
    get_cortex_instances,
    create_cortex_instance,
    update_cortex_instance,
    delete_cortex_instance,
    get_analyzer_by_uuid,
    get_analyzers_by_instance,
    get_responder_by_uuid,
    get_responders_by_instance,
    get_job_by_uuid,
    get_jobs,
    create_cortex_job,
    update_cortex_job,
    delete_cortex_job,
    create_or_update_analyzer,
    create_or_update_responder
)
from app.db.crud.observable import get_observable_by_uuid
from app.db.crud.case import get_case_by_uuid
from app.api.v1.schemas.cortex import (
    CortexInstanceResponse,
    CortexInstanceCreate,
    CortexInstanceUpdate,
    CortexAnalyzerResponse,
    CortexResponderResponse,
    CortexJobResponse,
    CortexJobCreate,
    CortexJobUpdate,
    AnalysisRequest,
    ResponseRequest,
    SyncRequest,
    SyncResponse,
    CortexHealthCheck
)
from app.auth.dependencies import get_current_user
from app.db.models import User, UserRole
from app.db.models.enums import WorkerType, JobStatus
from app.core import tracing
from app.core.api_management import APIManagement
from app.core.pagination import (
    PaginatedResponse,
    PaginationParams,
    get_pagination,
    AutoPaginator
)
from app.integrations.cortex_client import cortex_manager, CortexError

router = APIRouter()


# Cortex Instance Management

@router.get("/instances", response_model=PaginatedResponse[CortexInstanceResponse])
@APIManagement.rate_limit(operation_type="read")
async def list_cortex_instances(
    request: Request,
    enabled_only: bool = Query(False, description="Show only enabled instances"),
    pagination: PaginationParams = Depends(get_pagination),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List Cortex instances"""
    
    # Only admins can view Cortex instances
    if current_user.role not in [UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    instances = await get_cortex_instances(
        db=db,
        skip=pagination.skip,
        limit=pagination.limit,
        enabled_only=enabled_only
    )

    # Convert to response format with statistics
    instance_responses = []
    for instance in instances:
        analyzer_count = len([a for a in instance.analyzers if a.enabled])
        responder_count = len([r for r in instance.responders if r.enabled])
        active_jobs = len([j for j in instance.jobs if j.status in [JobStatus.WAITING, JobStatus.IN_PROGRESS]])
        
        instance_responses.append(
            CortexInstanceResponse.from_model(
                instance, 
                analyzer_count=analyzer_count,
                responder_count=responder_count,
                active_jobs=active_jobs
            )
        )

    paginator = AutoPaginator(
        data=instance_responses,
        total_count=len(instance_responses),
        page=pagination.page,
        page_size=pagination.limit
    )

    tracing.info("Cortex instances listed", 
                 count=len(instance_responses),
                 user_id=current_user.id)

    return paginator.get_response()


@router.post("/instances", response_model=CortexInstanceResponse, status_code=status.HTTP_201_CREATED)
@APIManagement.rate_limit(operation_type="write")
async def create_cortex_instance_endpoint(
    request: Request,
    instance_data: CortexInstanceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create new Cortex instance"""
    
    # Only admins can create Cortex instances
    if current_user.role not in [UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        # Encrypt API key before storing (simplified - should use proper encryption)
        instance = await create_cortex_instance(db, instance_data)
        
        # Add to cortex manager
        cortex_manager.add_instance(instance)

        tracing.info("Cortex instance created",
                     instance_id=str(instance.uuid),
                     instance_name=instance.name,
                     user_id=current_user.id)

        return CortexInstanceResponse.from_model(instance)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        tracing.error(f"Failed to create Cortex instance: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/instances/{instance_id}", response_model=CortexInstanceResponse)
@APIManagement.rate_limit(operation_type="read")
async def get_cortex_instance(
    request: Request,
    instance_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific Cortex instance"""
    
    # Only admins can view Cortex instances
    if current_user.role not in [UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    instance = await get_cortex_instance_by_uuid(db, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Cortex instance not found")

    # Calculate statistics
    analyzer_count = len([a for a in instance.analyzers if a.enabled])
    responder_count = len([r for r in instance.responders if r.enabled])
    active_jobs = len([j for j in instance.jobs if j.status in [JobStatus.WAITING, JobStatus.IN_PROGRESS]])

    tracing.info("Cortex instance retrieved",
                 instance_id=str(instance_id),
                 user_id=current_user.id)

    return CortexInstanceResponse.from_model(
        instance,
        analyzer_count=analyzer_count,
        responder_count=responder_count,
        active_jobs=active_jobs
    )


@router.put("/instances/{instance_id}", response_model=CortexInstanceResponse)
@APIManagement.rate_limit(operation_type="write")
async def update_cortex_instance_endpoint(
    request: Request,
    instance_id: UUID,
    updates: CortexInstanceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update Cortex instance"""
    
    # Only admins can update Cortex instances
    if current_user.role not in [UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    instance = await get_cortex_instance_by_uuid(db, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Cortex instance not found")

    try:
        updated_instance = await update_cortex_instance(db, instance, updates)
        
        # Update cortex manager
        cortex_manager.remove_instance(instance.name)
        cortex_manager.add_instance(updated_instance)

        tracing.info("Cortex instance updated",
                     instance_id=str(instance_id),
                     user_id=current_user.id)

        return CortexInstanceResponse.from_model(updated_instance)

    except Exception as e:
        tracing.error(f"Failed to update Cortex instance: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
@APIManagement.rate_limit(operation_type="write")
async def delete_cortex_instance_endpoint(
    request: Request,
    instance_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete Cortex instance"""
    
    # Only admins can delete Cortex instances
    if current_user.role not in [UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    instance = await get_cortex_instance_by_uuid(db, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Cortex instance not found")

    try:
        await delete_cortex_instance(db, instance)
        
        # Remove from cortex manager
        cortex_manager.remove_instance(instance.name)

        tracing.info("Cortex instance deleted",
                     instance_id=str(instance_id),
                     user_id=current_user.id)

    except Exception as e:
        tracing.error(f"Failed to delete Cortex instance: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Analyzer Management

@router.get("/instances/{instance_id}/analyzers", response_model=List[CortexAnalyzerResponse])
@APIManagement.rate_limit(operation_type="read")
async def list_analyzers(
    request: Request,
    instance_id: UUID,
    enabled_only: bool = Query(False, description="Show only enabled analyzers"),
    data_type: Optional[str] = Query(None, description="Filter by data type"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List analyzers for Cortex instance"""
    
    # Only analysts and above can view analyzers
    if current_user.role not in [UserRole.ADMIN, UserRole.ORG_ADMIN, UserRole.ANALYST]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    instance = await get_cortex_instance_by_uuid(db, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Cortex instance not found")

    analyzers = await get_analyzers_by_instance(
        db=db,
        instance_id=instance.id,
        enabled_only=enabled_only,
        data_type=data_type
    )

    analyzer_responses = [CortexAnalyzerResponse.from_model(analyzer) for analyzer in analyzers]

    tracing.info("Analyzers listed",
                 instance_id=str(instance_id),
                 count=len(analyzer_responses),
                 user_id=current_user.id)

    return analyzer_responses


# Responder Management

@router.get("/instances/{instance_id}/responders", response_model=List[CortexResponderResponse])
@APIManagement.rate_limit(operation_type="read")
async def list_responders(
    request: Request,
    instance_id: UUID,
    enabled_only: bool = Query(False, description="Show only enabled responders"),
    data_type: Optional[str] = Query(None, description="Filter by data type"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List responders for Cortex instance"""
    
    # Only analysts and above can view responders
    if current_user.role not in [UserRole.ADMIN, UserRole.ORG_ADMIN, UserRole.ANALYST]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    instance = await get_cortex_instance_by_uuid(db, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Cortex instance not found")

    responders = await get_responders_by_instance(
        db=db,
        instance_id=instance.id,
        enabled_only=enabled_only,
        data_type=data_type
    )

    responder_responses = [CortexResponderResponse.from_model(responder) for responder in responders]

    tracing.info("Responders listed",
                 instance_id=str(instance_id),
                 count=len(responder_responses),
                 user_id=current_user.id)

    return responder_responses


# Job Management

@router.get("/jobs", response_model=PaginatedResponse[CortexJobResponse])
@APIManagement.rate_limit(operation_type="read")
async def list_jobs(
    request: Request,
    status_filter: Optional[JobStatus] = Query(None, description="Filter by job status"),
    observable_id: Optional[UUID] = Query(None, description="Filter by observable"),
    case_id: Optional[UUID] = Query(None, description="Filter by case"),
    pagination: PaginationParams = Depends(get_pagination),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List Cortex jobs"""
    
    # Only analysts and above can view jobs
    if current_user.role not in [UserRole.ADMIN, UserRole.ORG_ADMIN, UserRole.ANALYST]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    jobs = await get_jobs(
        db=db,
        skip=pagination.skip,
        limit=pagination.limit,
        status_filter=status_filter,
        user_id=current_user.id if current_user.role == UserRole.ANALYST else None
    )

    job_responses = [CortexJobResponse.from_model(job) for job in jobs]

    paginator = AutoPaginator(
        data=job_responses,
        total_count=len(job_responses),
        page=pagination.page,
        page_size=pagination.limit
    )

    tracing.info("Cortex jobs listed",
                 count=len(job_responses),
                 user_id=current_user.id)

    return paginator.get_response()


@router.get("/jobs/{job_id}", response_model=CortexJobResponse)
@APIManagement.rate_limit(operation_type="read")
async def get_cortex_job(
    request: Request,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific Cortex job"""
    
    job = await get_job_by_uuid(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Cortex job not found")

    # Verify access permissions
    if current_user.role == UserRole.ANALYST and job.created_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    tracing.info("Cortex job retrieved",
                 job_id=str(job_id),
                 user_id=current_user.id)

    return CortexJobResponse.from_model(job)


# Analysis Operations

@router.post("/analyze", response_model=CortexJobResponse, status_code=status.HTTP_201_CREATED)
@APIManagement.rate_limit(operation_type="write")
async def run_analysis(
    request: Request,
    analysis_request: AnalysisRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Run analysis on observable"""
    
    # Only analysts and above can run analysis
    if current_user.role not in [UserRole.ADMIN, UserRole.ORG_ADMIN, UserRole.ANALYST]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Get analyzer
    analyzer = await get_analyzer_by_uuid(db, analysis_request.analyzer_id)
    if not analyzer:
        raise HTTPException(status_code=404, detail="Analyzer not found")

    if not analyzer.enabled or not analyzer.is_available:
        raise HTTPException(status_code=400, detail="Analyzer not available")

    # Get observable
    observable = await get_observable_by_uuid(db, analysis_request.observable_id)
    if not observable:
        raise HTTPException(status_code=404, detail="Observable not found")

    # Verify access to observable's case
    # (This would need proper organization/case access verification)

    try:
        # Create job record
        job_data = CortexJobCreate(
            cortex_job_id=f"pending-{int(time.time())}",  # Temporary ID
            worker_type=WorkerType.ANALYZER,
            status=JobStatus.WAITING,
            parameters=analysis_request.parameters,
            observable_id=observable.id
        )

        job = await create_cortex_job(
            db=db,
            job_data=job_data,
            cortex_instance_id=analyzer.cortex_instance_id,
            created_by_id=current_user.id,
            analyzer_id=analyzer.id
        )

        # Queue analysis in background
        background_tasks.add_task(
            _run_analysis_background,
            analyzer.cortex_instance.name,
            analyzer.name,
            observable.value,
            observable.type.value,
            analysis_request.parameters,
            job.uuid
        )

        tracing.info("Analysis job created",
                     job_id=str(job.uuid),
                     analyzer_name=analyzer.name,
                     observable_id=str(analysis_request.observable_id),
                     user_id=current_user.id)

        return CortexJobResponse.from_model(job)

    except Exception as e:
        tracing.error(f"Failed to create analysis job: {e}")
        raise HTTPException(status_code=500, detail="Failed to create analysis job")


async def _run_analysis_background(
    instance_name: str,
    analyzer_name: str,
    observable_data: str,
    observable_type: str,
    parameters: dict,
    job_uuid: UUID
):
    """Background task to run analysis"""
    try:
        # This would need proper database session management
        # and error handling in a real implementation
        result = await cortex_manager.run_analysis(
            instance_name=instance_name,
            analyzer_name=analyzer_name,
            observable_data=observable_data,
            observable_type=observable_type,
            parameters=parameters
        )
        
        # Update job with results
        logger.info(f"Analysis completed for job {job_uuid}: {result}")
        
    except Exception as e:
        logger.error(f"Analysis failed for job {job_uuid}: {e}")


# Sync Operations

@router.post("/sync", response_model=SyncResponse)
@APIManagement.rate_limit(operation_type="write")
async def sync_cortex_workers(
    request: Request,
    sync_request: SyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Sync analyzers and responders from Cortex instance"""
    
    # Only admins can sync
    if current_user.role not in [UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    instance = await get_cortex_instance_by_uuid(db, sync_request.instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Cortex instance not found")

    try:
        start_time = time.time()
        
        # Sync workers
        stats = await cortex_manager.sync_workers(instance)
        
        duration = time.time() - start_time

        tracing.info("Cortex sync completed",
                     instance_id=str(sync_request.instance_id),
                     analyzers=stats['analyzers'],
                     responders=stats['responders'],
                     errors=stats['errors'],
                     user_id=current_user.id)

        return SyncResponse(
            instance_id=sync_request.instance_id,
            analyzers_synced=stats['analyzers'],
            responders_synced=stats['responders'],
            errors=stats['errors'],
            duration=duration
        )

    except CortexError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        tracing.error(f"Failed to sync Cortex workers: {e}")
        raise HTTPException(status_code=500, detail="Sync failed")


# Health Check

@router.get("/instances/{instance_id}/health", response_model=CortexHealthCheck)
@APIManagement.rate_limit(operation_type="read")
async def check_instance_health(
    request: Request,
    instance_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check Cortex instance health"""
    
    # Only admins and org admins can check health
    if current_user.role not in [UserRole.ADMIN, UserRole.ORG_ADMIN]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    instance = await get_cortex_instance_by_uuid(db, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Cortex instance not found")

    try:
        client = cortex_manager.get_client(instance.name)
        if not client:
            cortex_manager.add_instance(instance)
            client = cortex_manager.get_client(instance.name)

        health = await client.health_check()

        return CortexHealthCheck(
            instance_id=instance_id,
            instance_name=instance.name,
            status=health['status'],
            version=health.get('version'),
            response_time=health['response_time'],
            error=health.get('error')
        )

    except Exception as e:
        return CortexHealthCheck(
            instance_id=instance_id,
            instance_name=instance.name,
            status='unhealthy',
            response_time=0.0,
            error=str(e)
        )