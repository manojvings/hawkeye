# app/db/crud/case.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import joinedload, selectinload
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from loguru import logger

from app.db.models import Case, Organization, User, Task, Observable
from app.db.models.enums import CaseStatus, Severity, TLP, ResolutionStatus, ImpactStatus
from app.api.v1.schemas.cases import CaseCreate, CaseUpdate
from app.core.case_utils import CaseNumberGenerator, CaseStatusTransition


async def generate_unique_case_number(db: AsyncSession, organization: Organization) -> str:
    """Generate a unique case number for the organization"""
    max_attempts = 10

    for _ in range(max_attempts):
        case_number = CaseNumberGenerator.generate_case_number(organization.name)

        # Check if this number already exists
        existing = await db.execute(
            select(Case).filter(Case.case_number == case_number)
        )
        if not existing.scalars().first():
            return case_number

    # Fallback if we can't generate a unique number
    raise ValueError("Unable to generate unique case number")


async def get_case_by_uuid(db: AsyncSession, case_uuid: UUID) -> Optional[Case]:
    """Get case by UUID with relationships loaded"""
    try:
        result = await db.execute(
            select(Case)
            .options(
                joinedload(Case.organization),
                joinedload(Case.assignee),
                joinedload(Case.created_by)
            )
            .filter(Case.uuid == case_uuid)
        )
        return result.scalars().first()
    except Exception as e:
        logger.error(f"Error retrieving case by UUID {case_uuid}: {e}")
        return None


async def get_case_by_number(db: AsyncSession, case_number: str) -> Optional[Case]:
    """Get case by case number"""
    try:
        result = await db.execute(
            select(Case)
            .options(
                joinedload(Case.organization),
                joinedload(Case.assignee),
                joinedload(Case.created_by)
            )
            .filter(Case.case_number == case_number)
        )
        return result.scalars().first()
    except Exception as e:
        logger.error(f"Error retrieving case by number {case_number}: {e}")
        return None


async def get_organization_cases(
        db: AsyncSession,
        organization_id: int,
        skip: int = 0,
        limit: int = 50,
        status_filter: Optional[CaseStatus] = None,
        assignee_id: Optional[int] = None,
        severity_filter: Optional[Severity] = None,
        search_term: Optional[str] = None
) -> List[Case]:
    """Get cases for an organization with filters"""
    try:
        query = select(Case).filter(Case.organization_id == organization_id)

        # Apply filters
        if status_filter:
            query = query.filter(Case.status == status_filter)

        if assignee_id is not None:
            if assignee_id == 0:  # Unassigned cases
                query = query.filter(Case.assignee_id.is_(None))
            else:
                query = query.filter(Case.assignee_id == assignee_id)

        if severity_filter:
            query = query.filter(Case.severity == severity_filter)

        if search_term:
            search_pattern = f"%{search_term}%"
            query = query.filter(
                or_(
                    Case.title.ilike(search_pattern),
                    Case.description.ilike(search_pattern),
                    Case.case_number.ilike(search_pattern)
                )
            )

        # Order by updated_at desc (most recent first)
        query = query.order_by(Case.updated_at.desc())

        # Add pagination
        query = query.offset(skip).limit(limit)

        # Load relationships
        query = query.options(
            joinedload(Case.assignee),
            joinedload(Case.created_by)
        )

        result = await db.execute(query)
        return result.scalars().unique().all()

    except Exception as e:
        logger.error(f"Error retrieving organization cases: {e}")
        return []


async def create_case(
        db: AsyncSession,
        case_data: CaseCreate,
        organization_id: int,
        creator_id: int,
        assignee_id: Optional[int] = None
) -> Case:
    """Create a new case"""
    try:
        # Get organization for case number generation
        org_result = await db.execute(
            select(Organization).filter(Organization.id == organization_id)
        )
        organization = org_result.scalars().first()

        # Generate unique case number
        case_number = await generate_unique_case_number(db, organization)

        # Create case
        case = Case(
            case_number=case_number,
            title=case_data.title,
            description=case_data.description,
            severity=case_data.severity,
            tlp=case_data.tlp,
            status=CaseStatus.OPEN,
            tags=case_data.tags or [],
            custom_fields=case_data.custom_fields or {},
            due_date=case_data.due_date,
            summary=case_data.summary,
            impact_status=case_data.impact_status,
            resolution_status=case_data.resolution_status,
            case_template=case_data.case_template,
            organization_id=organization_id,
            created_by_id=creator_id,
            assignee_id=assignee_id
        )

        db.add(case)
        await db.commit()
        await db.refresh(case)

        # Load relationships
        await db.refresh(case, ["organization", "assignee", "created_by"])

        logger.info(f"Case created: {case.case_number} by user {creator_id}")
        return case

    except Exception as e:
        logger.error(f"Failed to create case: {e}")
        await db.rollback()
        raise


async def update_case(
        db: AsyncSession,
        case: Case,
        updates: CaseUpdate,
        editor_id: int
) -> Case:
    """Update case details"""
    try:
        update_data = updates.dict(exclude_unset=True)

        # Handle status transition validation
        if 'status' in update_data:
            new_status = update_data['status']
            if not CaseStatusTransition.is_valid_transition(case.status.value, new_status.value):
                raise ValueError(
                    f"Invalid status transition from {case.status.value} to {new_status.value}"
                )

            # Set closed_at timestamp if resolving/duplicating
            if new_status in [CaseStatus.RESOLVED, CaseStatus.DUPLICATED] and case.status == CaseStatus.OPEN:
                case.closed_at = datetime.now(timezone.utc)
            elif new_status == CaseStatus.OPEN and case.status in [CaseStatus.RESOLVED, CaseStatus.DUPLICATED]:
                case.closed_at = None

        # Handle assignee by email
        if 'assignee_email' in update_data:
            assignee_email = update_data.pop('assignee_email')
            if assignee_email:
                # Find user by email
                user_result = await db.execute(
                    select(User).filter(User.email == assignee_email)
                )
                assignee = user_result.scalars().first()
                if not assignee:
                    raise ValueError(f"User with email {assignee_email} not found")
                case.assignee_id = assignee.id
            else:
                case.assignee_id = None

        # Update other fields
        for field, value in update_data.items():
            if hasattr(case, field):
                setattr(case, field, value)

        await db.commit()
        await db.refresh(case)

        # Reload relationships
        await db.refresh(case, ["organization", "assignee", "created_by"])

        logger.info(f"Case {case.case_number} updated by user {editor_id}")
        return case

    except Exception as e:
        logger.error(f"Failed to update case {case.case_number}: {e}")
        await db.rollback()
        raise


async def delete_case(db: AsyncSession, case: Case) -> bool:
    """Delete a case (soft delete by setting status to closed)"""
    try:
        case.status = CaseStatus.CLOSED
        case.closed_at = datetime.now(timezone.utc)

        await db.commit()
        logger.info(f"Case {case.case_number} closed (soft delete)")
        return True

    except Exception as e:
        logger.error(f"Failed to delete case {case.case_number}: {e}")
        await db.rollback()
        return False


async def get_case_stats(db: AsyncSession, case_id: int) -> Dict[str, int]:
    """Get case statistics (task and observable counts)"""
    try:
        task_count = await db.scalar(
            select(func.count(Task.id)).filter(Task.case_id == case_id)
        )

        observable_count = await db.scalar(
            select(func.count(Observable.id)).filter(Observable.case_id == case_id)
        )

        return {
            "task_count": task_count or 0,
            "observable_count": observable_count or 0
        }

    except Exception as e:
        logger.error(f"Error getting case stats: {e}")
        return {"task_count": 0, "observable_count": 0}


async def get_user_assigned_cases(
        db: AsyncSession,
        user_id: int,
        organization_id: Optional[int] = None,
        status_filter: Optional[CaseStatus] = None,
        skip: int = 0,
        limit: int = 50
) -> List[Case]:
    """Get cases assigned to a specific user"""
    try:
        query = select(Case).filter(Case.assignee_id == user_id)

        if organization_id:
            query = query.filter(Case.organization_id == organization_id)

        if status_filter:
            query = query.filter(Case.status == status_filter)

        query = query.order_by(Case.updated_at.desc())
        query = query.offset(skip).limit(limit)

        query = query.options(
            joinedload(Case.organization),
            joinedload(Case.created_by)
        )

        result = await db.execute(query)
        return result.scalars().unique().all()

    except Exception as e:
        logger.error(f"Error getting user assigned cases: {e}")
        return []