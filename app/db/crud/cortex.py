# app/db/crud/cortex.py
"""CRUD operations for Cortex integration"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import and_, func, or_
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from loguru import logger

from app.db.models.cortex import CortexInstance, CortexAnalyzer, CortexResponder, CortexJob
from app.db.models.enums import JobStatus, WorkerType
from app.api.v1.schemas.cortex import (
    CortexInstanceCreate, CortexInstanceUpdate,
    CortexJobCreate, CortexJobUpdate
)


# Cortex Instance CRUD

async def get_cortex_instance_by_uuid(db: AsyncSession, instance_uuid: UUID) -> Optional[CortexInstance]:
    """Get Cortex instance by UUID"""
    try:
        result = await db.execute(
            select(CortexInstance)
            .options(
                selectinload(CortexInstance.analyzers),
                selectinload(CortexInstance.responders)
            )
            .filter(CortexInstance.uuid == instance_uuid)
        )
        return result.scalars().first()
    except Exception as e:
        logger.error(f"Error retrieving Cortex instance by UUID {instance_uuid}: {e}")
        return None


async def get_cortex_instance_by_name(db: AsyncSession, name: str) -> Optional[CortexInstance]:
    """Get Cortex instance by name"""
    try:
        result = await db.execute(
            select(CortexInstance)
            .options(
                selectinload(CortexInstance.analyzers),
                selectinload(CortexInstance.responders)
            )
            .filter(CortexInstance.name == name)
        )
        return result.scalars().first()
    except Exception as e:
        logger.error(f"Error retrieving Cortex instance by name {name}: {e}")
        return None


async def get_cortex_instances(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    enabled_only: bool = False
) -> List[CortexInstance]:
    """Get list of Cortex instances"""
    try:
        query = select(CortexInstance)
        
        if enabled_only:
            query = query.filter(CortexInstance.enabled == True)
        
        query = query.offset(skip).limit(limit).order_by(CortexInstance.name)
        
        result = await db.execute(query)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error retrieving Cortex instances: {e}")
        return []


async def create_cortex_instance(
    db: AsyncSession,
    instance_data: CortexInstanceCreate
) -> CortexInstance:
    """Create new Cortex instance"""
    try:
        # Check if name already exists
        existing = await get_cortex_instance_by_name(db, instance_data.name)
        if existing:
            raise ValueError(f"Cortex instance with name '{instance_data.name}' already exists")

        instance = CortexInstance(
            name=instance_data.name,
            url=instance_data.url,
            api_key=instance_data.api_key,  # Should be encrypted before storing
            enabled=instance_data.enabled,
            included_organizations=instance_data.included_organizations,
            excluded_organizations=instance_data.excluded_organizations,
            verify_ssl=instance_data.verify_ssl,
            timeout=instance_data.timeout,
            max_concurrent_jobs=instance_data.max_concurrent_jobs
        )

        db.add(instance)
        await db.commit()
        await db.refresh(instance)

        logger.info(f"Cortex instance created: {instance.name}")
        return instance

    except Exception as e:
        logger.error(f"Failed to create Cortex instance: {e}")
        await db.rollback()
        raise


async def update_cortex_instance(
    db: AsyncSession,
    instance: CortexInstance,
    updates: CortexInstanceUpdate
) -> CortexInstance:
    """Update Cortex instance"""
    try:
        update_data = updates.dict(exclude_unset=True)

        for field, value in update_data.items():
            if hasattr(instance, field):
                setattr(instance, field, value)

        await db.commit()
        await db.refresh(instance)

        logger.info(f"Cortex instance updated: {instance.name}")
        return instance

    except Exception as e:
        logger.error(f"Failed to update Cortex instance: {e}")
        await db.rollback()
        raise


async def delete_cortex_instance(db: AsyncSession, instance: CortexInstance) -> bool:
    """Delete Cortex instance"""
    try:
        await db.delete(instance)
        await db.commit()

        logger.info(f"Cortex instance deleted: {instance.name}")
        return True

    except Exception as e:
        logger.error(f"Failed to delete Cortex instance: {e}")
        await db.rollback()
        raise


# Cortex Analyzer CRUD

async def get_analyzer_by_uuid(db: AsyncSession, analyzer_uuid: UUID) -> Optional[CortexAnalyzer]:
    """Get analyzer by UUID"""
    try:
        result = await db.execute(
            select(CortexAnalyzer)
            .options(joinedload(CortexAnalyzer.cortex_instance))
            .filter(CortexAnalyzer.uuid == analyzer_uuid)
        )
        return result.scalars().first()
    except Exception as e:
        logger.error(f"Error retrieving analyzer by UUID {analyzer_uuid}: {e}")
        return None


async def get_analyzers_by_instance(
    db: AsyncSession,
    instance_id: int,
    enabled_only: bool = False,
    data_type: Optional[str] = None
) -> List[CortexAnalyzer]:
    """Get analyzers for Cortex instance"""
    try:
        query = select(CortexAnalyzer).filter(CortexAnalyzer.cortex_instance_id == instance_id)
        
        if enabled_only:
            query = query.filter(CortexAnalyzer.enabled == True)
        
        if data_type:
            query = query.filter(CortexAnalyzer.data_types.contains([data_type]))
        
        query = query.order_by(CortexAnalyzer.name)
        
        result = await db.execute(query)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error retrieving analyzers: {e}")
        return []


async def create_or_update_analyzer(
    db: AsyncSession,
    instance_id: int,
    analyzer_data: Dict[str, Any]
) -> CortexAnalyzer:
    """Create or update analyzer from Cortex sync"""
    try:
        # Check if analyzer exists
        result = await db.execute(
            select(CortexAnalyzer).filter(
                and_(
                    CortexAnalyzer.cortex_instance_id == instance_id,
                    CortexAnalyzer.name == analyzer_data['name']
                )
            )
        )
        existing = result.scalars().first()

        if existing:
            # Update existing
            existing.version = analyzer_data.get('version', existing.version)
            existing.description = analyzer_data.get('description', existing.description)
            existing.data_types = analyzer_data.get('dataTypeList', existing.data_types)
            existing.max_tlp = analyzer_data.get('maxTlp', existing.max_tlp)
            existing.max_pap = analyzer_data.get('maxPap', existing.max_pap)
            existing.configuration = analyzer_data.get('configuration', existing.configuration)
            existing.is_available = True
            existing.last_sync = datetime.now(timezone.utc)
            
            analyzer = existing
        else:
            # Create new
            analyzer = CortexAnalyzer(
                name=analyzer_data['name'],
                display_name=analyzer_data.get('displayName', analyzer_data['name']),
                version=analyzer_data.get('version', '1.0'),
                description=analyzer_data.get('description'),
                data_types=analyzer_data.get('dataTypeList', []),
                max_tlp=analyzer_data.get('maxTlp', 3),
                max_pap=analyzer_data.get('maxPap', 3),
                configuration=analyzer_data.get('configuration', {}),
                cortex_instance_id=instance_id,
                last_sync=datetime.now(timezone.utc),
                is_available=True
            )
            db.add(analyzer)

        await db.commit()
        await db.refresh(analyzer)
        return analyzer

    except Exception as e:
        logger.error(f"Failed to create/update analyzer: {e}")
        await db.rollback()
        raise


# Cortex Responder CRUD

async def get_responder_by_uuid(db: AsyncSession, responder_uuid: UUID) -> Optional[CortexResponder]:
    """Get responder by UUID"""
    try:
        result = await db.execute(
            select(CortexResponder)
            .options(joinedload(CortexResponder.cortex_instance))
            .filter(CortexResponder.uuid == responder_uuid)
        )
        return result.scalars().first()
    except Exception as e:
        logger.error(f"Error retrieving responder by UUID {responder_uuid}: {e}")
        return None


async def get_responders_by_instance(
    db: AsyncSession,
    instance_id: int,
    enabled_only: bool = False,
    data_type: Optional[str] = None
) -> List[CortexResponder]:
    """Get responders for Cortex instance"""
    try:
        query = select(CortexResponder).filter(CortexResponder.cortex_instance_id == instance_id)
        
        if enabled_only:
            query = query.filter(CortexResponder.enabled == True)
        
        if data_type:
            query = query.filter(CortexResponder.data_types.contains([data_type]))
        
        query = query.order_by(CortexResponder.name)
        
        result = await db.execute(query)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error retrieving responders: {e}")
        return []


async def create_or_update_responder(
    db: AsyncSession,
    instance_id: int,
    responder_data: Dict[str, Any]
) -> CortexResponder:
    """Create or update responder from Cortex sync"""
    try:
        # Check if responder exists
        result = await db.execute(
            select(CortexResponder).filter(
                and_(
                    CortexResponder.cortex_instance_id == instance_id,
                    CortexResponder.name == responder_data['name']
                )
            )
        )
        existing = result.scalars().first()

        if existing:
            # Update existing
            existing.version = responder_data.get('version', existing.version)
            existing.description = responder_data.get('description', existing.description)
            existing.data_types = responder_data.get('dataTypeList', existing.data_types)
            existing.max_tlp = responder_data.get('maxTlp', existing.max_tlp)
            existing.max_pap = responder_data.get('maxPap', existing.max_pap)
            existing.configuration = responder_data.get('configuration', existing.configuration)
            existing.is_available = True
            existing.last_sync = datetime.now(timezone.utc)
            
            responder = existing
        else:
            # Create new
            responder = CortexResponder(
                name=responder_data['name'],
                display_name=responder_data.get('displayName', responder_data['name']),
                version=responder_data.get('version', '1.0'),
                description=responder_data.get('description'),
                data_types=responder_data.get('dataTypeList', []),
                max_tlp=responder_data.get('maxTlp', 3),
                max_pap=responder_data.get('maxPap', 3),
                configuration=responder_data.get('configuration', {}),
                cortex_instance_id=instance_id,
                last_sync=datetime.now(timezone.utc),
                is_available=True
            )
            db.add(responder)

        await db.commit()
        await db.refresh(responder)
        return responder

    except Exception as e:
        logger.error(f"Failed to create/update responder: {e}")
        await db.rollback()
        raise


# Cortex Job CRUD

async def get_job_by_uuid(db: AsyncSession, job_uuid: UUID) -> Optional[CortexJob]:
    """Get job by UUID"""
    try:
        result = await db.execute(
            select(CortexJob)
            .options(
                joinedload(CortexJob.cortex_instance),
                joinedload(CortexJob.analyzer),
                joinedload(CortexJob.responder),
                joinedload(CortexJob.observable),
                joinedload(CortexJob.case),
                joinedload(CortexJob.created_by)
            )
            .filter(CortexJob.uuid == job_uuid)
        )
        return result.scalars().first()
    except Exception as e:
        logger.error(f"Error retrieving job by UUID {job_uuid}: {e}")
        return None


async def get_job_by_cortex_id(db: AsyncSession, cortex_job_id: str) -> Optional[CortexJob]:
    """Get job by Cortex job ID"""
    try:
        result = await db.execute(
            select(CortexJob)
            .options(
                joinedload(CortexJob.cortex_instance),
                joinedload(CortexJob.analyzer),
                joinedload(CortexJob.responder)
            )
            .filter(CortexJob.cortex_job_id == cortex_job_id)
        )
        return result.scalars().first()
    except Exception as e:
        logger.error(f"Error retrieving job by Cortex ID {cortex_job_id}: {e}")
        return None


async def get_jobs(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    status_filter: Optional[JobStatus] = None,
    observable_id: Optional[int] = None,
    case_id: Optional[int] = None,
    user_id: Optional[int] = None
) -> List[CortexJob]:
    """Get jobs with filters"""
    try:
        query = select(CortexJob).options(
            joinedload(CortexJob.cortex_instance),
            joinedload(CortexJob.analyzer),
            joinedload(CortexJob.responder),
            joinedload(CortexJob.created_by)
        )
        
        if status_filter:
            query = query.filter(CortexJob.status == status_filter)
        
        if observable_id:
            query = query.filter(CortexJob.observable_id == observable_id)
        
        if case_id:
            query = query.filter(CortexJob.case_id == case_id)
        
        if user_id:
            query = query.filter(CortexJob.created_by_id == user_id)
        
        query = query.order_by(CortexJob.created_at.desc()).offset(skip).limit(limit)
        
        result = await db.execute(query)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error retrieving jobs: {e}")
        return []


async def create_cortex_job(
    db: AsyncSession,
    job_data: CortexJobCreate,
    cortex_instance_id: int,
    created_by_id: int,
    analyzer_id: Optional[int] = None,
    responder_id: Optional[int] = None
) -> CortexJob:
    """Create new Cortex job"""
    try:
        job = CortexJob(
            cortex_job_id=job_data.cortex_job_id,
            worker_type=job_data.worker_type,
            status=job_data.status or JobStatus.WAITING,
            parameters=job_data.parameters or {},
            cortex_instance_id=cortex_instance_id,
            analyzer_id=analyzer_id,
            responder_id=responder_id,
            observable_id=job_data.observable_id,
            case_id=job_data.case_id,
            created_by_id=created_by_id
        )

        db.add(job)
        await db.commit()
        await db.refresh(job)

        logger.info(f"Cortex job created: {job.cortex_job_id}")
        return job

    except Exception as e:
        logger.error(f"Failed to create Cortex job: {e}")
        await db.rollback()
        raise


async def update_cortex_job(
    db: AsyncSession,
    job: CortexJob,
    updates: CortexJobUpdate
) -> CortexJob:
    """Update Cortex job"""
    try:
        update_data = updates.dict(exclude_unset=True)

        for field, value in update_data.items():
            if hasattr(job, field):
                setattr(job, field, value)

        # Update timestamps based on status
        if updates.status == JobStatus.IN_PROGRESS and not job.started_at:
            job.started_at = datetime.now(timezone.utc)
        elif updates.status in [JobStatus.SUCCESS, JobStatus.FAILURE] and not job.ended_at:
            job.ended_at = datetime.now(timezone.utc)
            if job.started_at:
                job.duration = (job.ended_at - job.started_at).total_seconds()

        await db.commit()
        await db.refresh(job)

        logger.info(f"Cortex job updated: {job.cortex_job_id} -> {job.status}")
        return job

    except Exception as e:
        logger.error(f"Failed to update Cortex job: {e}")
        await db.rollback()
        raise


async def delete_cortex_job(db: AsyncSession, job: CortexJob) -> bool:
    """Delete Cortex job"""
    try:
        await db.delete(job)
        await db.commit()

        logger.info(f"Cortex job deleted: {job.cortex_job_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to delete Cortex job: {e}")
        await db.rollback()
        raise