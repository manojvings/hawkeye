# app/api/v1/endpoints/case_templates.py
"""
Case Template management endpoints for standardized case creation
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from app.db.database import get_db
from app.db.crud.case_template import (
    get_case_template_by_uuid,
    get_case_template_by_name,
    get_organization_case_templates,
    create_case_template,
    update_case_template,
    delete_case_template,
    create_case_from_template,
    get_template_usage_stats,
    bulk_template_operation,
    get_task_template_by_uuid,
    create_task_template,
    update_task_template,
    delete_task_template
)
from app.db.crud.organization import verify_organization_access, get_organization_by_uuid
from app.db.crud.user import get_user_by_email
from app.api.v1.schemas.case_templates import (
    CaseTemplateResponse,
    CaseTemplateCreate,
    CaseTemplateUpdate,
    CaseTemplateSummary,
    CaseFromTemplateRequest,
    TaskTemplateResponse,
    TaskTemplateCreate,
    TaskTemplateUpdate,
    TemplateUsageStats,
    BulkTemplateOperation
)
from app.api.v1.schemas.cases import CaseResponse
from app.auth.dependencies import get_current_user
from app.db.models import User, UserRole
from app.core import tracing
from app.core.api_management import APIManagement
from app.core.pagination import (
    PaginatedResponse,
    PaginationParams,
    get_pagination,
    AutoPaginator
)

router = APIRouter()


@router.get("/", response_model=PaginatedResponse[CaseTemplateSummary])
@APIManagement.rate_limit(operation_type="read")
async def list_case_templates(
    request: Request,
    organization_id: UUID,
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search templates by name or description"),
    pagination: PaginationParams = Depends(get_pagination),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List case templates for an organization"""
    
    # Verify organization access
    org = await get_organization_by_uuid(db, organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    if not await verify_organization_access(db, current_user.id, org.id):
        raise HTTPException(status_code=403, detail="Access denied to organization")

    # Get templates
    templates = await get_organization_case_templates(
        db=db,
        organization_id=org.id,
        skip=pagination.skip,
        limit=pagination.limit,
        is_active_filter=is_active,
        search_term=search
    )

    # Convert to summaries
    template_summaries = [CaseTemplateSummary.from_model(template) for template in templates]

    # Create paginated response
    paginator = AutoPaginator(
        data=template_summaries,
        total_count=len(template_summaries),  # This is simplified; ideally get actual count
        page=pagination.page,
        page_size=pagination.limit
    )

    tracing.info("Case templates listed", 
                 organization_id=str(organization_id),
                 count=len(template_summaries),
                 user_id=current_user.id)

    return paginator.get_response()


@router.post("/", response_model=CaseTemplateResponse, status_code=status.HTTP_201_CREATED)
@APIManagement.rate_limit(operation_type="write")
async def create_new_case_template(
    request: Request,
    organization_id: UUID,
    template_data: CaseTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new case template"""
    
    # Verify organization access and permissions
    org = await get_organization_by_uuid(db, organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    if not await verify_organization_access(db, current_user.id, org.id, min_role=UserRole.ANALYST):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        # Create template
        template = await create_case_template(
            db=db,
            template_data=template_data,
            organization_id=org.id,
            creator_id=current_user.id
        )

        tracing.info("Case template created",
                     template_id=str(template.uuid),
                     template_name=template.name,
                     organization_id=str(organization_id),
                     user_id=current_user.id)

        return CaseTemplateResponse.from_model(template)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        tracing.error(f"Failed to create case template: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{template_id}", response_model=CaseTemplateResponse)
@APIManagement.rate_limit(operation_type="read")
async def get_case_template(
    request: Request,
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific case template"""
    
    template = await get_case_template_by_uuid(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Case template not found")

    # Verify organization access
    if not await verify_organization_access(db, current_user.id, template.organization_id):
        raise HTTPException(status_code=403, detail="Access denied")

    tracing.info("Case template retrieved",
                 template_id=str(template_id),
                 user_id=current_user.id)

    return CaseTemplateResponse.from_model(template)


@router.put("/{template_id}", response_model=CaseTemplateResponse)
@APIManagement.rate_limit(operation_type="write")
async def update_case_template_details(
    request: Request,
    template_id: UUID,
    updates: CaseTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a case template"""
    
    template = await get_case_template_by_uuid(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Case template not found")

    # Verify organization access and permissions
    if not await verify_organization_access(db, current_user.id, template.organization_id, min_role=UserRole.ANALYST):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        updated_template = await update_case_template(
            db=db,
            case_template=template,
            updates=updates,
            editor_id=current_user.id
        )

        tracing.info("Case template updated",
                     template_id=str(template_id),
                     user_id=current_user.id)

        return CaseTemplateResponse.from_model(updated_template)

    except Exception as e:
        tracing.error(f"Failed to update case template: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
@APIManagement.rate_limit(operation_type="write")
async def delete_case_template_endpoint(
    request: Request,
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a case template"""
    
    template = await get_case_template_by_uuid(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Case template not found")

    # Verify organization access and permissions
    if not await verify_organization_access(db, current_user.id, template.organization_id, min_role=UserRole.ORG_ADMIN):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        await delete_case_template(db, template)

        tracing.info("Case template deleted",
                     template_id=str(template_id),
                     user_id=current_user.id)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        tracing.error(f"Failed to delete case template: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{template_id}/create-case", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
@APIManagement.rate_limit(operation_type="write")
async def create_case_from_template_endpoint(
    request: Request,
    template_id: UUID,
    case_request: CaseFromTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a case from a template"""
    
    template = await get_case_template_by_uuid(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Case template not found")

    # Verify organization access
    if not await verify_organization_access(db, current_user.id, template.organization_id, min_role=UserRole.ANALYST):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Handle assignee
    assignee_id = None
    if case_request.assignee_email:
        assignee = await get_user_by_email(db, case_request.assignee_email)
        if not assignee:
            raise HTTPException(status_code=400, detail="Assignee not found")
        
        # Verify assignee has access to organization
        if not await verify_organization_access(db, assignee.id, template.organization_id):
            raise HTTPException(status_code=400, detail="Assignee does not have access to organization")
        
        assignee_id = assignee.id

    try:
        # Override template_id in request with the path parameter
        case_request.template_id = template_id

        case = await create_case_from_template(
            db=db,
            request=case_request,
            organization_id=template.organization_id,
            creator_id=current_user.id,
            assignee_id=assignee_id
        )

        tracing.info("Case created from template",
                     case_id=str(case.uuid),
                     case_number=case.case_number,
                     template_id=str(template_id),
                     user_id=current_user.id)

        return CaseResponse.from_model(case)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        tracing.error(f"Failed to create case from template: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{template_id}/usage-stats", response_model=List[TemplateUsageStats])
@APIManagement.rate_limit(operation_type="read")
async def get_template_usage_statistics(
    request: Request,
    organization_id: UUID,
    days_back: int = Query(30, ge=1, le=365, description="Days to look back for statistics"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get template usage statistics"""
    
    # Verify organization access
    org = await get_organization_by_uuid(db, organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    if not await verify_organization_access(db, current_user.id, org.id, min_role=UserRole.ANALYST):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        stats = await get_template_usage_stats(
            db=db,
            organization_id=org.id,
            days_back=days_back
        )

        tracing.info("Template usage stats retrieved",
                     organization_id=str(organization_id),
                     days_back=days_back,
                     user_id=current_user.id)

        return [TemplateUsageStats(**stat) for stat in stats]

    except Exception as e:
        tracing.error(f"Failed to get template usage stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk-operation", response_model=dict)
@APIManagement.rate_limit(operation_type="write")
async def bulk_template_operations(
    request: Request,
    organization_id: UUID,
    operation: BulkTemplateOperation,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Perform bulk operations on templates"""
    
    # Verify organization access and permissions
    org = await get_organization_by_uuid(db, organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    min_role = UserRole.ORG_ADMIN if operation.operation == 'delete' else UserRole.ANALYST
    if not await verify_organization_access(db, current_user.id, org.id, min_role=min_role):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        results = await bulk_template_operation(
            db=db,
            template_ids=operation.template_ids,
            operation=operation.operation,
            organization_id=org.id,
            operator_id=current_user.id
        )

        tracing.info("Bulk template operation completed",
                     operation=operation.operation,
                     template_count=len(operation.template_ids),
                     organization_id=str(organization_id),
                     user_id=current_user.id)

        return results

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        tracing.error(f"Failed bulk template operation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Task Template endpoints

@router.post("/{template_id}/tasks", response_model=TaskTemplateResponse, status_code=status.HTTP_201_CREATED)
@APIManagement.rate_limit(operation_type="write")
async def create_task_template_endpoint(
    request: Request,
    template_id: UUID,
    task_data: TaskTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new task template"""
    
    template = await get_case_template_by_uuid(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Case template not found")

    # Verify organization access and permissions
    if not await verify_organization_access(db, current_user.id, template.organization_id, min_role=UserRole.ANALYST):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        task_template = await create_task_template(
            db=db,
            task_data=task_data,
            case_template_id=template.id,
            creator_id=current_user.id
        )

        tracing.info("Task template created",
                     task_template_id=str(task_template.uuid),
                     template_id=str(template_id),
                     user_id=current_user.id)

        return TaskTemplateResponse.from_model(task_template)

    except Exception as e:
        tracing.error(f"Failed to create task template: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/tasks/{task_template_id}", response_model=TaskTemplateResponse)
@APIManagement.rate_limit(operation_type="write")
async def update_task_template_endpoint(
    request: Request,
    task_template_id: UUID,
    updates: TaskTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a task template"""
    
    task_template = await get_task_template_by_uuid(db, task_template_id)
    if not task_template:
        raise HTTPException(status_code=404, detail="Task template not found")

    # Verify organization access and permissions
    if not await verify_organization_access(db, current_user.id, task_template.case_template.organization_id, min_role=UserRole.ANALYST):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        updated_task_template = await update_task_template(
            db=db,
            task_template=task_template,
            updates=updates,
            editor_id=current_user.id
        )

        tracing.info("Task template updated",
                     task_template_id=str(task_template_id),
                     user_id=current_user.id)

        return TaskTemplateResponse.from_model(updated_task_template)

    except Exception as e:
        tracing.error(f"Failed to update task template: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/tasks/{task_template_id}", status_code=status.HTTP_204_NO_CONTENT)
@APIManagement.rate_limit(operation_type="write")
async def delete_task_template_endpoint(
    request: Request,
    task_template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a task template"""
    
    task_template = await get_task_template_by_uuid(db, task_template_id)
    if not task_template:
        raise HTTPException(status_code=404, detail="Task template not found")

    # Verify organization access and permissions
    if not await verify_organization_access(db, current_user.id, task_template.case_template.organization_id, min_role=UserRole.ANALYST):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        await delete_task_template(db, task_template)

        tracing.info("Task template deleted",
                     task_template_id=str(task_template_id),
                     user_id=current_user.id)

    except Exception as e:
        tracing.error(f"Failed to delete task template: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")