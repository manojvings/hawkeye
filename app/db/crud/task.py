# app/db/crud/task.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import joinedload
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from loguru import logger

from app.db.models import Task, Case, User, TaskStatus
from app.api.v1.schemas.tasks import TaskCreate, TaskUpdate


async def get_task_by_uuid(db: AsyncSession, task_uuid: UUID) -> Optional[Task]:
    """Get task by UUID with relationships loaded"""
    try:
        result = await db.execute(
            select(Task)
            .options(
                joinedload(Task.case),
                joinedload(Task.assignee),
                joinedload(Task.created_by)
            )
            .filter(Task.uuid == task_uuid)
        )
        return result.scalars().first()
    except Exception as e:
        logger.error(f"Error retrieving task by UUID {task_uuid}: {e}")
        return None


async def get_case_tasks(
        db: AsyncSession,
        case_id: int,
        skip: int = 0,
        limit: int = 50,
        status_filter: Optional[TaskStatus] = None,
        assignee_id: Optional[int] = None
) -> List[Task]:
    """Get tasks for a case with filters"""
    try:
        query = select(Task).filter(Task.case_id == case_id)

        # Apply filters
        if status_filter:
            query = query.filter(Task.status == status_filter)

        if assignee_id is not None:
            if assignee_id == 0:  # Unassigned tasks
                query = query.filter(Task.assignee_id.is_(None))
            else:
                query = query.filter(Task.assignee_id == assignee_id)

        # Order by order_index then created_at
        query = query.order_by(Task.order_index.asc(), Task.created_at.asc())

        # Add pagination
        query = query.offset(skip).limit(limit)

        # Load relationships
        query = query.options(
            joinedload(Task.assignee),
            joinedload(Task.created_by)
        )

        result = await db.execute(query)
        return result.scalars().unique().all()

    except Exception as e:
        logger.error(f"Error retrieving case tasks: {e}")
        return []


async def create_task(
        db: AsyncSession,
        task_data: TaskCreate,
        case_id: int,
        creator_id: int,
        assignee_id: Optional[int] = None
) -> Task:
    """Create a new task"""
    try:
        # Get the next order index for this case
        max_order = await db.scalar(
            select(func.coalesce(func.max(Task.order_index), -1))
            .filter(Task.case_id == case_id)
        )
        next_order = (max_order or -1) + 1

        # Create task
        task = Task(
            title=task_data.title,
            description=task_data.description,
            status=TaskStatus.PENDING,
            order_index=task_data.order_index if task_data.order_index is not None else next_order,
            due_date=task_data.due_date,
            case_id=case_id,
            created_by_id=creator_id,
            assignee_id=assignee_id
        )

        db.add(task)
        await db.commit()
        await db.refresh(task)

        # Load relationships
        await db.refresh(task, ["case", "assignee", "created_by"])

        logger.info(f"Task created: {task.title} for case {case_id} by user {creator_id}")
        return task

    except Exception as e:
        logger.error(f"Failed to create task: {e}")
        await db.rollback()
        raise


async def update_task(
        db: AsyncSession,
        task: Task,
        updates: TaskUpdate,
        editor_id: int
) -> Task:
    """Update task details"""
    try:
        update_data = updates.dict(exclude_unset=True)

        # Handle status change to completed
        if 'status' in update_data:
            new_status = update_data['status']
            if new_status == TaskStatus.COMPLETED and task.status != TaskStatus.COMPLETED:
                task.completed_at = datetime.now(timezone.utc)
            elif new_status != TaskStatus.COMPLETED and task.status == TaskStatus.COMPLETED:
                task.completed_at = None

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
                task.assignee_id = assignee.id
            else:
                task.assignee_id = None

        # Update other fields
        for field, value in update_data.items():
            if hasattr(task, field):
                setattr(task, field, value)

        await db.commit()
        await db.refresh(task)

        # Reload relationships
        await db.refresh(task, ["case", "assignee", "created_by"])

        logger.info(f"Task {task.title} updated by user {editor_id}")
        return task

    except Exception as e:
        logger.error(f"Failed to update task {task.title}: {e}")
        await db.rollback()
        raise


async def delete_task(db: AsyncSession, task: Task) -> bool:
    """Delete a task (hard delete)"""
    try:
        await db.delete(task)
        await db.commit()
        logger.info(f"Task {task.title} deleted")
        return True

    except Exception as e:
        logger.error(f"Failed to delete task {task.title}: {e}")
        await db.rollback()
        return False


async def reorder_tasks(
        db: AsyncSession,
        case_id: int,
        task_orders: List[Dict[str, Any]]
) -> bool:
    """Reorder tasks in a case"""
    try:
        # task_orders should be list of {"task_uuid": UUID, "order_index": int}
        for task_order in task_orders:
            task_uuid = task_order["task_uuid"]
            new_order = task_order["order_index"]
            
            # Update the task order
            result = await db.execute(
                select(Task).filter(
                    Task.uuid == task_uuid,
                    Task.case_id == case_id
                )
            )
            task = result.scalars().first()
            
            if task:
                task.order_index = new_order

        await db.commit()
        logger.info(f"Tasks reordered for case {case_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to reorder tasks for case {case_id}: {e}")
        await db.rollback()
        return False


async def get_user_assigned_tasks(
        db: AsyncSession,
        user_id: int,
        case_id: Optional[int] = None,
        status_filter: Optional[TaskStatus] = None,
        skip: int = 0,
        limit: int = 50
) -> List[Task]:
    """Get tasks assigned to a specific user"""
    try:
        query = select(Task).filter(Task.assignee_id == user_id)

        if case_id:
            query = query.filter(Task.case_id == case_id)

        if status_filter:
            query = query.filter(Task.status == status_filter)

        # Order by due date then created date
        query = query.order_by(
            Task.due_date.asc().nullslast(),
            Task.created_at.desc()
        )
        query = query.offset(skip).limit(limit)

        query = query.options(
            joinedload(Task.case),
            joinedload(Task.created_by)
        )

        result = await db.execute(query)
        return result.scalars().unique().all()

    except Exception as e:
        logger.error(f"Error getting user assigned tasks: {e}")
        return []


async def get_task_stats_by_case(db: AsyncSession, case_id: int) -> Dict[str, int]:
    """Get task statistics for a case"""
    try:
        # Count tasks by status
        pending_count = await db.scalar(
            select(func.count(Task.id)).filter(
                Task.case_id == case_id,
                Task.status == TaskStatus.PENDING
            )
        )

        in_progress_count = await db.scalar(
            select(func.count(Task.id)).filter(
                Task.case_id == case_id,
                Task.status == TaskStatus.IN_PROGRESS
            )
        )

        completed_count = await db.scalar(
            select(func.count(Task.id)).filter(
                Task.case_id == case_id,
                Task.status == TaskStatus.COMPLETED
            )
        )

        total_count = await db.scalar(
            select(func.count(Task.id)).filter(Task.case_id == case_id)
        )

        return {
            "total": total_count or 0,
            "pending": pending_count or 0,
            "in_progress": in_progress_count or 0,
            "completed": completed_count or 0
        }

    except Exception as e:
        logger.error(f"Error getting task stats for case {case_id}: {e}")
        return {"total": 0, "pending": 0, "in_progress": 0, "completed": 0}


async def bulk_update_task_status(
        db: AsyncSession,
        task_uuids: List[UUID],
        new_status: TaskStatus,
        case_id: int
) -> int:
    """Bulk update task status for multiple tasks"""
    try:
        # Get tasks to update
        result = await db.execute(
            select(Task).filter(
                Task.uuid.in_(task_uuids),
                Task.case_id == case_id
            )
        )
        tasks = result.scalars().all()

        updated_count = 0
        for task in tasks:
            old_status = task.status
            task.status = new_status
            
            # Handle completion timestamp
            if new_status == TaskStatus.COMPLETED and old_status != TaskStatus.COMPLETED:
                task.completed_at = datetime.now(timezone.utc)
            elif new_status != TaskStatus.COMPLETED and old_status == TaskStatus.COMPLETED:
                task.completed_at = None
                
            updated_count += 1

        await db.commit()
        logger.info(f"Bulk updated {updated_count} tasks to status {new_status.value}")
        return updated_count

    except Exception as e:
        logger.error(f"Failed to bulk update task status: {e}")
        await db.rollback()
        return 0