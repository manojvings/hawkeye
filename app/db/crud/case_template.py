# app/db/crud/case_template.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import joinedload, selectinload
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone, timedelta
from loguru import logger

from app.db.models.case_template import CaseTemplate, TaskTemplate
from app.db.models import Organization, User, Case, Task
from app.db.models.enums import Severity, TLP, TaskStatus
from app.api.v1.schemas.case_templates import (
    CaseTemplateCreate, CaseTemplateUpdate, TaskTemplateCreate, TaskTemplateUpdate,
    CaseFromTemplateRequest
)
from app.core.case_utils import CaseNumberGenerator


async def get_case_template_by_uuid(db: AsyncSession, template_uuid: UUID) -> Optional[CaseTemplate]:
    """Get case template by UUID with relationships loaded"""
    try:
        result = await db.execute(
            select(CaseTemplate)
            .options(
                joinedload(CaseTemplate.organization),
                joinedload(CaseTemplate.created_by),
                selectinload(CaseTemplate.task_templates).joinedload(TaskTemplate.created_by)
            )
            .filter(CaseTemplate.uuid == template_uuid)
        )
        return result.scalars().first()
    except Exception as e:
        logger.error(f"Error retrieving case template by UUID {template_uuid}: {e}")
        return None


async def get_case_template_by_name(
    db: AsyncSession, 
    organization_id: int, 
    name: str
) -> Optional[CaseTemplate]:
    """Get case template by name within organization"""
    try:
        result = await db.execute(
            select(CaseTemplate)
            .options(
                joinedload(CaseTemplate.organization),
                joinedload(CaseTemplate.created_by)
            )
            .filter(
                CaseTemplate.organization_id == organization_id,
                CaseTemplate.name == name
            )
        )
        return result.scalars().first()
    except Exception as e:
        logger.error(f"Error retrieving case template by name {name}: {e}")
        return None


async def get_organization_case_templates(
    db: AsyncSession,
    organization_id: int,
    skip: int = 0,
    limit: int = 50,
    is_active_filter: Optional[bool] = None,
    search_term: Optional[str] = None
) -> List[CaseTemplate]:
    """Get case templates for an organization with filters"""
    try:
        query = select(CaseTemplate).filter(CaseTemplate.organization_id == organization_id)

        # Apply filters
        if is_active_filter is not None:
            query = query.filter(CaseTemplate.is_active == is_active_filter)

        if search_term:
            search_pattern = f"%{search_term}%"
            query = query.filter(
                or_(
                    CaseTemplate.name.ilike(search_pattern),
                    CaseTemplate.display_name.ilike(search_pattern),
                    CaseTemplate.description.ilike(search_pattern)
                )
            )

        # Order by usage count desc, then by name
        query = query.order_by(CaseTemplate.usage_count.desc(), CaseTemplate.name)

        # Add pagination
        query = query.offset(skip).limit(limit)

        # Load relationships
        query = query.options(
            joinedload(CaseTemplate.organization),
            joinedload(CaseTemplate.created_by),
            selectinload(CaseTemplate.task_templates)
        )

        result = await db.execute(query)
        return result.scalars().unique().all()

    except Exception as e:
        logger.error(f"Error retrieving organization case templates: {e}")
        return []


async def create_case_template(
    db: AsyncSession,
    template_data: CaseTemplateCreate,
    organization_id: int,
    creator_id: int
) -> CaseTemplate:
    """Create a new case template with task templates"""
    try:
        # Check if template name already exists in organization
        existing = await get_case_template_by_name(db, organization_id, template_data.name)
        if existing:
            raise ValueError(f"Case template with name '{template_data.name}' already exists")

        # Create case template
        case_template = CaseTemplate(
            name=template_data.name,
            display_name=template_data.display_name,
            title_prefix=template_data.title_prefix,
            description=template_data.description,
            severity=template_data.severity,
            tlp=template_data.tlp,
            pap=template_data.pap,
            flag=template_data.flag,
            tags=template_data.tags or [],
            custom_fields=template_data.custom_fields or {},
            summary=template_data.summary,
            organization_id=organization_id,
            created_by_id=creator_id
        )

        db.add(case_template)
        await db.flush()  # Get the ID for task templates

        # Create task templates
        for task_data in template_data.task_templates:
            task_template = TaskTemplate(
                title=task_data.title,
                description=task_data.description,
                group=task_data.group,
                order_index=task_data.order_index,
                flag=task_data.flag,
                assignee_role=task_data.assignee_role,
                due_days_offset=task_data.due_days_offset,
                depends_on=task_data.depends_on or [],
                case_template_id=case_template.id,
                created_by_id=creator_id
            )
            db.add(task_template)

        await db.commit()
        await db.refresh(case_template)

        # Load relationships
        await db.refresh(case_template, ["organization", "created_by", "task_templates"])

        logger.info(f"Case template created: {case_template.name} by user {creator_id}")
        return case_template

    except Exception as e:
        logger.error(f"Failed to create case template: {e}")
        await db.rollback()
        raise


async def update_case_template(
    db: AsyncSession,
    case_template: CaseTemplate,
    updates: CaseTemplateUpdate,
    editor_id: int
) -> CaseTemplate:
    """Update case template details"""
    try:
        update_data = updates.dict(exclude_unset=True)

        # Update fields
        for field, value in update_data.items():
            if hasattr(case_template, field):
                setattr(case_template, field, value)

        await db.commit()
        await db.refresh(case_template)

        # Reload relationships
        await db.refresh(case_template, ["organization", "created_by", "task_templates"])

        logger.info(f"Case template {case_template.name} updated by user {editor_id}")
        return case_template

    except Exception as e:
        logger.error(f"Failed to update case template: {e}")
        await db.rollback()
        raise


async def delete_case_template(db: AsyncSession, case_template: CaseTemplate) -> bool:
    """Delete a case template"""
    try:
        # Check if template is being used by any cases
        cases_using_template = await db.scalar(
            select(func.count(Case.id)).filter(Case.case_template_id == case_template.id)
        )
        
        if cases_using_template > 0:
            raise ValueError(f"Cannot delete template: {cases_using_template} cases are using this template")

        await db.delete(case_template)
        await db.commit()

        logger.info(f"Case template {case_template.name} deleted")
        return True

    except Exception as e:
        logger.error(f"Failed to delete case template: {e}")
        await db.rollback()
        raise


async def create_case_from_template(
    db: AsyncSession,
    request: CaseFromTemplateRequest,
    organization_id: int,
    creator_id: int,
    assignee_id: Optional[int] = None
) -> Case:
    """Create a case from a template"""
    try:
        # Get the template
        template = await get_case_template_by_uuid(db, request.template_id)
        if not template:
            raise ValueError("Case template not found")
        
        if template.organization_id != organization_id:
            raise ValueError("Template not accessible to this organization")

        # Get organization for case number generation
        org_result = await db.execute(
            select(Organization).filter(Organization.id == organization_id)
        )
        organization = org_result.scalars().first()

        # Generate unique case number
        case_number = await CaseNumberGenerator.generate_case_number(organization.name)

        # Build case title with template prefix
        title = request.title
        if template.title_prefix:
            title = f"{template.title_prefix}: {title}"

        # Merge tags from template and request
        tags = list(set((template.tags or []) + (request.additional_tags or [])))

        # Merge custom fields
        custom_fields = (template.custom_fields or {}).copy()
        custom_fields.update(request.custom_field_overrides or {})

        # Create case
        case = Case(
            case_number=case_number,
            title=title,
            description=request.description or template.description,
            severity=request.severity or template.severity or Severity.MEDIUM,
            tlp=request.tlp or template.tlp or TLP.AMBER,
            tags=tags,
            custom_fields=custom_fields,
            summary=template.summary,
            case_template=template.name,  # For backward compatibility
            case_template_id=template.id,
            organization_id=organization_id,
            created_by_id=creator_id,
            assignee_id=assignee_id
        )

        db.add(case)
        await db.flush()  # Get case ID for tasks

        # Create tasks from template if requested
        if request.create_tasks and template.task_templates:
            for task_template in sorted(template.task_templates, key=lambda t: t.order_index):
                # Calculate due date if offset is specified
                due_date = None
                if task_template.due_days_offset is not None:
                    due_date = datetime.now(timezone.utc) + timedelta(days=task_template.due_days_offset)

                # Determine assignee based on role (simplified logic)
                task_assignee_id = assignee_id  # Default to case assignee
                
                task = Task(
                    title=task_template.title,
                    description=task_template.description,
                    group=task_template.group,
                    order_index=task_template.order_index,
                    flag=task_template.flag,
                    due_date=due_date,
                    case_id=case.id,
                    created_by_id=creator_id,
                    assignee_id=task_assignee_id
                )
                db.add(task)

        # Update template usage count
        template.usage_count += 1

        await db.commit()
        await db.refresh(case)

        # Load relationships
        await db.refresh(case, ["organization", "assignee", "created_by", "template", "tasks"])

        logger.info(f"Case created from template: {case.case_number} from {template.name}")
        return case

    except Exception as e:
        logger.error(f"Failed to create case from template: {e}")
        await db.rollback()
        raise


async def get_template_usage_stats(
    db: AsyncSession,
    organization_id: int,
    days_back: int = 30
) -> List[Dict[str, Any]]:
    """Get template usage statistics"""
    try:
        # Get templates with usage data
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        
        result = await db.execute(
            select(
                CaseTemplate,
                func.count(Case.id).label('cases_created'),
                func.max(Case.created_at).label('last_used'),
                func.avg(
                    func.extract('epoch', Case.closed_at - Case.created_at) / 86400
                ).label('avg_duration_days')
            )
            .outerjoin(Case, CaseTemplate.id == Case.case_template_id)
            .filter(
                CaseTemplate.organization_id == organization_id,
                or_(Case.created_at >= cutoff_date, Case.id.is_(None))
            )
            .group_by(CaseTemplate.id)
            .options(joinedload(CaseTemplate.organization))
        )

        stats = []
        for template, cases_created, last_used, avg_duration in result:
            stats.append({
                'template_id': template.uuid,
                'template_name': template.name,
                'display_name': template.display_name,
                'usage_count': template.usage_count,
                'cases_created': cases_created or 0,
                'last_used': last_used,
                'avg_case_duration': float(avg_duration) if avg_duration else None,
                'is_active': template.is_active
            })

        return sorted(stats, key=lambda x: x['cases_created'], reverse=True)

    except Exception as e:
        logger.error(f"Error getting template usage stats: {e}")
        return []


async def bulk_template_operation(
    db: AsyncSession,
    template_ids: List[UUID],
    operation: str,
    organization_id: int,
    operator_id: int
) -> Dict[str, Any]:
    """Perform bulk operations on templates"""
    try:
        # Get templates
        result = await db.execute(
            select(CaseTemplate).filter(
                CaseTemplate.uuid.in_(template_ids),
                CaseTemplate.organization_id == organization_id
            )
        )
        templates = result.scalars().all()

        if not templates:
            raise ValueError("No templates found")

        results = {'success': [], 'errors': []}

        for template in templates:
            try:
                if operation == 'activate':
                    template.is_active = True
                    results['success'].append(template.uuid)
                elif operation == 'deactivate':
                    template.is_active = False
                    results['success'].append(template.uuid)
                elif operation == 'delete':
                    # Check if template is in use
                    cases_using = await db.scalar(
                        select(func.count(Case.id)).filter(Case.case_template_id == template.id)
                    )
                    if cases_using > 0:
                        results['errors'].append({
                            'template_id': template.uuid,
                            'error': f'Template in use by {cases_using} cases'
                        })
                    else:
                        await db.delete(template)
                        results['success'].append(template.uuid)
            except Exception as e:
                results['errors'].append({
                    'template_id': template.uuid,
                    'error': str(e)
                })

        await db.commit()
        
        logger.info(f"Bulk template operation '{operation}' completed by user {operator_id}")
        return results

    except Exception as e:
        logger.error(f"Failed bulk template operation: {e}")
        await db.rollback()
        raise


# Task Template CRUD operations

async def get_task_template_by_uuid(db: AsyncSession, task_template_uuid: UUID) -> Optional[TaskTemplate]:
    """Get task template by UUID"""
    try:
        result = await db.execute(
            select(TaskTemplate)
            .options(
                joinedload(TaskTemplate.case_template).joinedload(CaseTemplate.organization),
                joinedload(TaskTemplate.created_by)
            )
            .filter(TaskTemplate.uuid == task_template_uuid)
        )
        return result.scalars().first()
    except Exception as e:
        logger.error(f"Error retrieving task template by UUID {task_template_uuid}: {e}")
        return None


async def create_task_template(
    db: AsyncSession,
    task_data: TaskTemplateCreate,
    case_template_id: int,
    creator_id: int
) -> TaskTemplate:
    """Create a new task template"""
    try:
        task_template = TaskTemplate(
            title=task_data.title,
            description=task_data.description,
            group=task_data.group,
            order_index=task_data.order_index,
            flag=task_data.flag,
            assignee_role=task_data.assignee_role,
            due_days_offset=task_data.due_days_offset,
            depends_on=task_data.depends_on or [],
            case_template_id=case_template_id,
            created_by_id=creator_id
        )

        db.add(task_template)
        await db.commit()
        await db.refresh(task_template)

        # Load relationships
        await db.refresh(task_template, ["case_template", "created_by"])

        logger.info(f"Task template created: {task_template.title}")
        return task_template

    except Exception as e:
        logger.error(f"Failed to create task template: {e}")
        await db.rollback()
        raise


async def update_task_template(
    db: AsyncSession,
    task_template: TaskTemplate,
    updates: TaskTemplateUpdate,
    editor_id: int
) -> TaskTemplate:
    """Update task template details"""
    try:
        update_data = updates.dict(exclude_unset=True)

        # Update fields
        for field, value in update_data.items():
            if hasattr(task_template, field):
                setattr(task_template, field, value)

        await db.commit()
        await db.refresh(task_template)

        logger.info(f"Task template {task_template.title} updated by user {editor_id}")
        return task_template

    except Exception as e:
        logger.error(f"Failed to update task template: {e}")
        await db.rollback()
        raise


async def delete_task_template(db: AsyncSession, task_template: TaskTemplate) -> bool:
    """Delete a task template"""
    try:
        await db.delete(task_template)
        await db.commit()

        logger.info(f"Task template {task_template.title} deleted")
        return True

    except Exception as e:
        logger.error(f"Failed to delete task template: {e}")
        await db.rollback()
        raise