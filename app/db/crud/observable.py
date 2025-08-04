# app/db/crud/observable.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import joinedload
from typing import Optional, List, Dict, Any
from uuid import UUID
from loguru import logger

from app.db.models import Observable, Case, User, ObservableType, TLP
from app.api.v1.schemas.observables import ObservableCreate, ObservableUpdate


async def get_observable_by_uuid(db: AsyncSession, observable_uuid: UUID) -> Optional[Observable]:
    """Get observable by UUID with relationships loaded"""
    try:
        result = await db.execute(
            select(Observable)
            .options(
                joinedload(Observable.case),
                joinedload(Observable.created_by)
            )
            .filter(Observable.uuid == observable_uuid)
        )
        return result.scalars().first()
    except Exception as e:
        logger.error(f"Error retrieving observable by UUID {observable_uuid}: {e}")
        return None


async def get_case_observables(
        db: AsyncSession,
        case_id: int,
        skip: int = 0,
        limit: int = 50,
        data_type_filter: Optional[ObservableType] = None,
        is_ioc_filter: Optional[bool] = None,
        search_term: Optional[str] = None
) -> List[Observable]:
    """Get observables for a case with filters"""
    try:
        query = select(Observable).filter(Observable.case_id == case_id)

        # Apply filters
        if data_type_filter:
            query = query.filter(Observable.data_type == data_type_filter)

        if is_ioc_filter is not None:
            query = query.filter(Observable.is_ioc == is_ioc_filter)

        if search_term:
            search_pattern = f"%{search_term}%"
            query = query.filter(
                or_(
                    Observable.data.ilike(search_pattern),
                    Observable.message.ilike(search_pattern),
                    Observable.source.ilike(search_pattern)
                )
            )

        # Order by created_at desc (most recent first)
        query = query.order_by(Observable.created_at.desc())

        # Add pagination
        query = query.offset(skip).limit(limit)

        # Load relationships
        query = query.options(joinedload(Observable.created_by))

        result = await db.execute(query)
        return result.scalars().unique().all()

    except Exception as e:
        logger.error(f"Error retrieving case observables: {e}")
        return []


async def get_global_observables(
        db: AsyncSession,
        organization_id: int,
        skip: int = 0,
        limit: int = 50,
        data_type_filter: Optional[ObservableType] = None,
        is_ioc_filter: Optional[bool] = None,
        search_term: Optional[str] = None
) -> List[Observable]:
    """Get observables across all cases in an organization"""
    try:
        # Join with Case to filter by organization
        query = (
            select(Observable)
            .join(Case, Observable.case_id == Case.id)
            .filter(Case.organization_id == organization_id)
        )

        # Apply filters
        if data_type_filter:
            query = query.filter(Observable.data_type == data_type_filter)

        if is_ioc_filter is not None:
            query = query.filter(Observable.is_ioc == is_ioc_filter)

        if search_term:
            search_pattern = f"%{search_term}%"
            query = query.filter(
                or_(
                    Observable.data.ilike(search_pattern),
                    Observable.message.ilike(search_pattern),
                    Observable.source.ilike(search_pattern)
                )
            )

        # Order by created_at desc
        query = query.order_by(Observable.created_at.desc())

        # Add pagination
        query = query.offset(skip).limit(limit)

        # Load relationships
        query = query.options(
            joinedload(Observable.case),
            joinedload(Observable.created_by)
        )

        result = await db.execute(query)
        return result.scalars().unique().all()

    except Exception as e:
        logger.error(f"Error retrieving global observables: {e}")
        return []


async def create_observable(
        db: AsyncSession,
        observable_data: ObservableCreate,
        case_id: Optional[int],
        creator_id: int
) -> Observable:
    """Create a new observable"""
    try:
        # Create observable
        observable = Observable(
            data_type=observable_data.data_type,
            data=observable_data.data.strip(),
            tlp=observable_data.tlp,
            is_ioc=observable_data.is_ioc,
            tags=observable_data.tags or [],
            source=observable_data.source,
            message=observable_data.message,
            case_id=case_id,
            created_by_id=creator_id
        )

        db.add(observable)
        await db.commit()
        await db.refresh(observable)

        # Load relationships
        if case_id:
            await db.refresh(observable, ["case", "created_by"])
        else:
            await db.refresh(observable, ["created_by"])

        logger.info(f"Observable created: {observable.data_type.value} - {observable.data[:50]} by user {creator_id}")
        return observable

    except Exception as e:
        logger.error(f"Failed to create observable: {e}")
        await db.rollback()
        raise


async def update_observable(
        db: AsyncSession,
        observable: Observable,
        updates: ObservableUpdate,
        editor_id: int
) -> Observable:
    """Update observable details"""
    try:
        update_data = updates.dict(exclude_unset=True)

        # Update fields
        for field, value in update_data.items():
            if hasattr(observable, field):
                if field == 'data' and value:
                    value = value.strip()
                setattr(observable, field, value)

        await db.commit()
        await db.refresh(observable)

        # Reload relationships
        if observable.case_id:
            await db.refresh(observable, ["case", "created_by"])
        else:
            await db.refresh(observable, ["created_by"])

        logger.info(f"Observable {observable.data} updated by user {editor_id}")
        return observable

    except Exception as e:
        logger.error(f"Failed to update observable {observable.data}: {e}")
        await db.rollback()
        raise


async def delete_observable(db: AsyncSession, observable: Observable) -> bool:
    """Delete an observable (hard delete)"""
    try:
        await db.delete(observable)
        await db.commit()
        logger.info(f"Observable {observable.data} deleted")
        return True

    except Exception as e:
        logger.error(f"Failed to delete observable {observable.data}: {e}")
        await db.rollback()
        return False


async def increment_sighted_count(db: AsyncSession, observable: Observable) -> Observable:
    """Increment the sighted count for an observable"""
    try:
        observable.sighted_count += 1
        await db.commit()
        await db.refresh(observable)
        
        logger.info(f"Observable {observable.data} sighted count incremented to {observable.sighted_count}")
        return observable

    except Exception as e:
        logger.error(f"Failed to increment sighted count for observable {observable.data}: {e}")
        await db.rollback()
        raise


async def find_similar_observables(
        db: AsyncSession,
        data: str,
        data_type: ObservableType,
        organization_id: int,
        exclude_observable_id: Optional[int] = None
) -> List[Observable]:
    """Find similar observables in the organization"""
    try:
        query = (
            select(Observable)
            .join(Case, Observable.case_id == Case.id)
            .filter(
                Case.organization_id == organization_id,
                Observable.data_type == data_type,
                Observable.data.ilike(f"%{data.strip()}%")
            )
        )

        if exclude_observable_id:
            query = query.filter(Observable.id != exclude_observable_id)

        query = query.options(
            joinedload(Observable.case),
            joinedload(Observable.created_by)
        )

        result = await db.execute(query)
        return result.scalars().unique().all()

    except Exception as e:
        logger.error(f"Error finding similar observables: {e}")
        return []


async def get_ioc_stats_by_case(db: AsyncSession, case_id: int) -> Dict[str, int]:
    """Get IOC statistics for a case"""
    try:
        # Count observables by type
        total_count = await db.scalar(
            select(func.count(Observable.id)).filter(Observable.case_id == case_id)
        )

        ioc_count = await db.scalar(
            select(func.count(Observable.id)).filter(
                Observable.case_id == case_id,
                Observable.is_ioc == True
            )
        )

        # Count by data type
        type_counts = {}
        for obs_type in ObservableType:
            count = await db.scalar(
                select(func.count(Observable.id)).filter(
                    Observable.case_id == case_id,
                    Observable.data_type == obs_type
                )
            )
            type_counts[obs_type.value] = count or 0

        return {
            "total": total_count or 0,
            "ioc": ioc_count or 0,
            "artifacts": (total_count or 0) - (ioc_count or 0),
            "by_type": type_counts
        }

    except Exception as e:
        logger.error(f"Error getting IOC stats for case {case_id}: {e}")
        return {"total": 0, "ioc": 0, "artifacts": 0, "by_type": {}}


async def bulk_update_observable_tags(
        db: AsyncSession,
        observable_uuids: List[UUID],
        tags: List[str],
        case_id: int
) -> int:
    """Bulk update tags for multiple observables"""
    try:
        # Get observables to update
        result = await db.execute(
            select(Observable).filter(
                Observable.uuid.in_(observable_uuids),
                Observable.case_id == case_id
            )
        )
        observables = result.scalars().all()

        updated_count = 0
        for observable in observables:
            # Merge tags (add new ones without duplicates)
            existing_tags = set(observable.tags or [])
            new_tags = set(tags)
            observable.tags = list(existing_tags.union(new_tags))
            updated_count += 1

        await db.commit()
        logger.info(f"Bulk updated tags for {updated_count} observables")
        return updated_count

    except Exception as e:
        logger.error(f"Failed to bulk update observable tags: {e}")
        await db.rollback()
        return 0


async def bulk_mark_as_ioc(
        db: AsyncSession,
        observable_uuids: List[UUID],
        case_id: int,
        is_ioc: bool = True
) -> int:
    """Bulk mark observables as IOC or artifact"""
    try:
        # Get observables to update
        result = await db.execute(
            select(Observable).filter(
                Observable.uuid.in_(observable_uuids),
                Observable.case_id == case_id
            )
        )
        observables = result.scalars().all()

        updated_count = 0
        for observable in observables:
            observable.is_ioc = is_ioc
            updated_count += 1

        await db.commit()
        logger.info(f"Bulk marked {updated_count} observables as {'IOC' if is_ioc else 'artifact'}")
        return updated_count

    except Exception as e:
        logger.error(f"Failed to bulk update IOC status: {e}")
        await db.rollback()
        return 0


async def search_observables_by_data(
        db: AsyncSession,
        search_data: str,
        organization_id: int,
        exact_match: bool = False
) -> List[Observable]:
    """Search observables by data value across organization"""
    try:
        if exact_match:
            query = (
                select(Observable)
                .join(Case, Observable.case_id == Case.id)
                .filter(
                    Case.organization_id == organization_id,
                    Observable.data == search_data.strip()
                )
            )
        else:
            search_pattern = f"%{search_data.strip()}%"
            query = (
                select(Observable)
                .join(Case, Observable.case_id == Case.id)
                .filter(
                    Case.organization_id == organization_id,
                    Observable.data.ilike(search_pattern)
                )
            )

        query = query.options(
            joinedload(Observable.case),
            joinedload(Observable.created_by)  
        ).order_by(Observable.created_at.desc())

        result = await db.execute(query)
        return result.scalars().unique().all()

    except Exception as e:
        logger.error(f"Error searching observables by data: {e}")
        return []