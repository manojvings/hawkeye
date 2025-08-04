# app/db/crud/alert.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import joinedload
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from loguru import logger

from app.db.models import Alert, Case, User, Organization
from app.db.models.enums import AlertStatus, Severity, TLP
from app.api.v1.schemas.alerts import AlertCreate, AlertUpdate


async def get_alert_by_uuid(db: AsyncSession, alert_uuid: UUID) -> Optional[Alert]:
    """Get alert by UUID with relationships loaded"""
    try:
        result = await db.execute(
            select(Alert)
            .options(
                joinedload(Alert.organization),
                joinedload(Alert.case),
                joinedload(Alert.created_by)
            )
            .filter(Alert.uuid == alert_uuid)
        )
        return result.scalars().first()
    except Exception as e:
        logger.error(f"Error retrieving alert by UUID {alert_uuid}: {e}")
        return None


async def get_alert_by_source_ref(
        db: AsyncSession, 
        source: str, 
        source_ref: str
) -> Optional[Alert]:
    """Get alert by source and source reference"""
    try:
        result = await db.execute(
            select(Alert).filter(
                Alert.source == source,
                Alert.source_ref == source_ref
            )
        )
        return result.scalars().first()
    except Exception as e:
        logger.error(f"Error retrieving alert by source ref {source}:{source_ref}: {e}")
        return None


async def get_organization_alerts(
        db: AsyncSession,
        organization_id: int,
        skip: int = 0,
        limit: int = 50,
        status_filter: Optional[AlertStatus] = None,
        severity_filter: Optional[Severity] = None,
        source_filter: Optional[str] = None,
        search_term: Optional[str] = None,
        include_imported: bool = True
) -> List[Alert]:
    """Get alerts for an organization with filters"""
    try:
        query = select(Alert).filter(Alert.organization_id == organization_id)

        # Apply filters
        if status_filter:
            query = query.filter(Alert.status == status_filter)

        if severity_filter:
            query = query.filter(Alert.severity == severity_filter)

        if source_filter:
            query = query.filter(Alert.source == source_filter)

        if not include_imported:
            query = query.filter(Alert.case_id.is_(None))

        if search_term:
            search_pattern = f"%{search_term}%"
            query = query.filter(
                or_(
                    Alert.title.ilike(search_pattern),
                    Alert.description.ilike(search_pattern),
                    Alert.source.ilike(search_pattern),
                    Alert.source_ref.ilike(search_pattern)
                )
            )

        # Order by created_at desc (most recent first)
        query = query.order_by(Alert.created_at.desc())

        # Add pagination
        query = query.offset(skip).limit(limit)

        # Load relationships
        query = query.options(
            joinedload(Alert.case),
            joinedload(Alert.created_by)
        )

        result = await db.execute(query)
        return result.scalars().unique().all()

    except Exception as e:
        logger.error(f"Error retrieving organization alerts: {e}")
        return []


async def create_alert(
        db: AsyncSession,
        alert_data: AlertCreate,
        organization_id: int,
        creator_id: Optional[int] = None
) -> Alert:
    """Create a new alert"""
    try:
        # Check for existing alert with same source_ref
        existing = await get_alert_by_source_ref(
            db, alert_data.source, alert_data.source_ref
        )
        if existing:
            raise ValueError(f"Alert with source_ref {alert_data.source_ref} already exists")

        # Create alert
        alert = Alert(
            type=alert_data.type,
            title=alert_data.title,
            description=alert_data.description,
            source=alert_data.source,
            source_ref=alert_data.source_ref,
            external_link=alert_data.external_link,
            severity=alert_data.severity,
            tlp=alert_data.tlp,
            pap=alert_data.pap,
            status=AlertStatus.NEW,
            date=alert_data.date,
            last_sync_date=alert_data.last_sync_date,
            read=alert_data.read,
            follow=alert_data.follow,
            tags=alert_data.tags or [],
            raw_data=alert_data.raw_data or {},
            observables=alert_data.observables or [],
            organization_id=organization_id,
            created_by_id=creator_id
        )

        db.add(alert)
        await db.commit()
        await db.refresh(alert)

        # Load relationships
        await db.refresh(alert, ["organization", "created_by"])

        logger.info(f"Alert created: {alert.source}:{alert.source_ref} by user {creator_id}")
        return alert

    except Exception as e:
        logger.error(f"Failed to create alert: {e}")
        await db.rollback()
        raise


async def update_alert(
        db: AsyncSession,
        alert: Alert,
        updates: AlertUpdate,
        editor_id: int
) -> Alert:
    """Update alert details"""
    try:
        update_data = updates.dict(exclude_unset=True)

        # Update fields
        for field, value in update_data.items():
            if hasattr(alert, field):
                setattr(alert, field, value)

        await db.commit()
        await db.refresh(alert)

        # Reload relationships
        await db.refresh(alert, ["organization", "case", "created_by"])

        logger.info(f"Alert {alert.source_ref} updated by user {editor_id}")
        return alert

    except Exception as e:
        logger.error(f"Failed to update alert {alert.source_ref}: {e}")
        await db.rollback()
        raise


async def delete_alert(db: AsyncSession, alert: Alert) -> bool:
    """Delete an alert (hard delete)"""
    try:
        await db.delete(alert)
        await db.commit()
        logger.info(f"Alert {alert.source_ref} deleted")
        return True

    except Exception as e:
        logger.error(f"Failed to delete alert {alert.source_ref}: {e}")
        await db.rollback()
        return False


async def promote_alert_to_case(
        db: AsyncSession,
        alert: Alert,
        case_title: Optional[str] = None,
        case_description: Optional[str] = None,
        assignee_id: Optional[int] = None,
        creator_id: int
) -> Case:
    """Promote an alert to a case"""
    try:
        from app.db.crud.case import create_case
        from app.api.v1.schemas.cases import CaseCreate

        # Prepare case data
        case_data = CaseCreate(
            title=case_title or alert.title,
            description=case_description or alert.description,
            severity=alert.severity,
            tlp=alert.tlp,
            tags=[f"source:{alert.source}"],
            custom_fields={
                "alert_source": alert.source,
                "alert_source_ref": alert.source_ref,
                "promoted_from_alert": str(alert.uuid)
            }
        )

        # Create the case
        case = await create_case(
            db=db,
            case_data=case_data,
            organization_id=alert.organization_id,
            creator_id=creator_id,
            assignee_id=assignee_id
        )

        # Link alert to case and update status
        alert.case_id = case.id
        alert.status = AlertStatus.IMPORTED
        alert.imported_at = datetime.now(timezone.utc)

        # Create observables from alert's embedded observables
        if alert.observables:
            from app.db.crud.observable import create_observable
            from app.api.v1.schemas.observables import ObservableCreate
            
            for obs_data in alert.observables:
                try:
                    observable_create = ObservableCreate(
                        data_type=obs_data.get("data_type", "other"),
                        data=obs_data.get("data", ""),
                        tlp=alert.tlp,
                        is_ioc=obs_data.get("is_ioc", False),
                        tags=obs_data.get("tags", []),
                        source=alert.source,
                        message=f"Imported from alert {alert.source_ref}"
                    )
                    
                    await create_observable(
                        db=db,
                        observable_data=observable_create,
                        case_id=case.id,
                        creator_id=creator_id
                    )
                except Exception as obs_error:
                    logger.warning(f"Failed to create observable from alert: {obs_error}")

        await db.commit()
        await db.refresh(alert)
        await db.refresh(case)

        logger.info(f"Alert {alert.source_ref} promoted to case {case.case_number}")
        return case

    except Exception as e:
        logger.error(f"Failed to promote alert {alert.source_ref} to case: {e}")
        await db.rollback()
        raise


async def bulk_update_alert_status(
        db: AsyncSession,
        alert_uuids: List[UUID],
        new_status: AlertStatus,
        organization_id: int
) -> int:
    """Bulk update alert status for multiple alerts"""
    try:
        # Get alerts to update
        result = await db.execute(
            select(Alert).filter(
                Alert.uuid.in_(alert_uuids),
                Alert.organization_id == organization_id
            )
        )
        alerts = result.scalars().all()

        updated_count = 0
        for alert in alerts:
            alert.status = new_status
            updated_count += 1

        await db.commit()
        logger.info(f"Bulk updated {updated_count} alerts to status {new_status.value}")
        return updated_count

    except Exception as e:
        logger.error(f"Failed to bulk update alert status: {e}")
        await db.rollback()
        return 0


async def get_alert_stats_by_organization(
        db: AsyncSession, 
        organization_id: int
) -> Dict[str, int]:
    """Get alert statistics for an organization"""
    try:
        # Count alerts by status
        new_count = await db.scalar(
            select(func.count(Alert.id)).filter(
                Alert.organization_id == organization_id,
                Alert.status == AlertStatus.NEW
            )
        )

        acknowledged_count = await db.scalar(
            select(func.count(Alert.id)).filter(
                Alert.organization_id == organization_id,
                Alert.status == AlertStatus.ACKNOWLEDGED
            )
        )

        imported_count = await db.scalar(
            select(func.count(Alert.id)).filter(
                Alert.organization_id == organization_id,
                Alert.status == AlertStatus.IMPORTED
            )
        )

        ignored_count = await db.scalar(
            select(func.count(Alert.id)).filter(
                Alert.organization_id == organization_id,
                Alert.status == AlertStatus.IGNORED
            )
        )

        total_count = await db.scalar(
            select(func.count(Alert.id)).filter(
                Alert.organization_id == organization_id
            )
        )

        return {
            "total": total_count or 0,
            "new": new_count or 0,
            "acknowledged": acknowledged_count or 0,
            "imported": imported_count or 0,
            "ignored": ignored_count or 0
        }

    except Exception as e:
        logger.error(f"Error getting alert stats for organization {organization_id}: {e}")
        return {"total": 0, "new": 0, "acknowledged": 0, "imported": 0, "ignored": 0}


async def get_alerts_by_source(
        db: AsyncSession,
        organization_id: int,
        source: str,
        skip: int = 0,
        limit: int = 50
) -> List[Alert]:
    """Get alerts from a specific source"""
    try:
        query = (
            select(Alert)
            .filter(
                Alert.organization_id == organization_id,
                Alert.source == source
            )
            .order_by(Alert.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        query = query.options(
            joinedload(Alert.case),
            joinedload(Alert.created_by)
        )

        result = await db.execute(query)
        return result.scalars().unique().all()

    except Exception as e:
        logger.error(f"Error getting alerts by source {source}: {e}")
        return []


async def acknowledge_alert(db: AsyncSession, alert: Alert, user_id: int) -> Alert:
    """Acknowledge an alert"""
    try:
        alert.status = AlertStatus.ACKNOWLEDGED
        
        # Add acknowledgment info to raw_data
        if not alert.raw_data:
            alert.raw_data = {}
        alert.raw_data["acknowledged_by"] = user_id
        alert.raw_data["acknowledged_at"] = datetime.now(timezone.utc).isoformat()

        await db.commit()
        await db.refresh(alert)

        logger.info(f"Alert {alert.source_ref} acknowledged by user {user_id}")
        return alert

    except Exception as e:
        logger.error(f"Failed to acknowledge alert {alert.source_ref}: {e}")
        await db.rollback()
        raise


async def ignore_alert(db: AsyncSession, alert: Alert, user_id: int, reason: Optional[str] = None) -> Alert:
    """Ignore an alert"""
    try:
        alert.status = AlertStatus.IGNORED
        
        # Add ignore info to raw_data
        if not alert.raw_data:
            alert.raw_data = {}
        alert.raw_data["ignored_by"] = user_id
        alert.raw_data["ignored_at"] = datetime.now(timezone.utc).isoformat()
        if reason:
            alert.raw_data["ignore_reason"] = reason

        await db.commit()
        await db.refresh(alert)

        logger.info(f"Alert {alert.source_ref} ignored by user {user_id}")
        return alert

    except Exception as e:
        logger.error(f"Failed to ignore alert {alert.source_ref}: {e}")
        await db.rollback()
        raise