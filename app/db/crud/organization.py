# app/db/crud/organization.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from sqlalchemy.orm import joinedload, selectinload
from typing import Optional, List, Dict, Any
from uuid import UUID
from loguru import logger

from app.db.models import Organization, UserOrganization, User, Case, UserRole
from app.api.v1.schemas.organizations import OrganizationCreate, OrganizationUpdate


async def get_organization_by_uuid(db: AsyncSession, org_uuid: UUID) -> Optional[Organization]:
    """Get organization by UUID"""
    try:
        result = await db.execute(
            select(Organization).filter(Organization.uuid == org_uuid)
        )
        org = result.scalars().first()
        if org:
            logger.debug(f"Organization found: {org.name}")
        return org
    except Exception as e:
        logger.error(f"Error retrieving organization by UUID {org_uuid}: {e}")
        return None


async def get_organization_by_name(db: AsyncSession, name: str) -> Optional[Organization]:
    """Get organization by name"""
    try:
        result = await db.execute(
            select(Organization).filter(Organization.name == name)
        )
        return result.scalars().first()
    except Exception as e:
        logger.error(f"Error retrieving organization by name {name}: {e}")
        return None


async def get_user_organizations(
        db: AsyncSession,
        user_id: int,
        skip: int = 0,
        limit: int = 50
) -> List[UserOrganization]:
    """Get all organizations a user belongs to"""
    try:
        result = await db.execute(
            select(UserOrganization)
            .options(
                joinedload(UserOrganization.organization),
                joinedload(UserOrganization.user)
            )
            .filter(UserOrganization.user_id == user_id)
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().unique().all()
    except Exception as e:
        logger.error(f"Error retrieving user organizations: {e}")
        return []


async def verify_organization_access(
        db: AsyncSession,
        user_id: int,
        org_uuid: UUID,
        required_roles: Optional[List[UserRole]] = None
) -> Optional[UserOrganization]:
    """Verify user has access to organization with optional role check"""
    try:
        query = select(UserOrganization).join(Organization).filter(
            UserOrganization.user_id == user_id,
            Organization.uuid == org_uuid
        )

        if required_roles:
            query = query.filter(UserOrganization.role.in_(required_roles))

        result = await db.execute(
            query.options(
                joinedload(UserOrganization.organization),
                joinedload(UserOrganization.user)
            )
        )

        membership = result.scalars().first()
        if membership:
            logger.debug(f"User {user_id} has access to org {org_uuid} with role {membership.role}")
        else:
            logger.warning(f"User {user_id} denied access to org {org_uuid}")

        return membership
    except Exception as e:
        logger.error(f"Error verifying organization access: {e}")
        return None


async def create_organization(
        db: AsyncSession,
        org_data: OrganizationCreate,
        creator_id: int
) -> Organization:
    """Create new organization and add creator as admin"""
    try:
        # Create organization
        org = Organization(
            name=org_data.name,
            description=org_data.description,
            settings=org_data.settings or {}
        )
        db.add(org)
        await db.flush()  # Get the ID without committing

        # Add creator as admin
        membership = UserOrganization(
            user_id=creator_id,
            organization_id=org.id,
            role=UserRole.ORG_ADMIN
        )
        db.add(membership)

        await db.commit()
        await db.refresh(org)

        logger.info(f"Organization created: {org.name} by user {creator_id}")
        return org

    except Exception as e:
        logger.error(f"Failed to create organization: {e}")
        await db.rollback()
        raise


async def update_organization(
        db: AsyncSession,
        org: Organization,
        updates: OrganizationUpdate
) -> Organization:
    """Update organization details"""
    try:
        update_data = updates.dict(exclude_unset=True)

        for field, value in update_data.items():
            if hasattr(org, field):
                setattr(org, field, value)

        await db.commit()
        await db.refresh(org)

        logger.info(f"Organization updated: {org.name}")
        return org

    except Exception as e:
        logger.error(f"Failed to update organization {org.name}: {e}")
        await db.rollback()
        raise


async def add_organization_member(
        db: AsyncSession,
        org_id: int,
        user_id: int,
        role: UserRole
) -> UserOrganization:
    """Add user to organization with specified role"""
    try:
        # Check if already a member
        existing = await db.execute(
            select(UserOrganization).filter(
                UserOrganization.organization_id == org_id,
                UserOrganization.user_id == user_id
            )
        )

        if existing.scalars().first():
            raise ValueError("User is already a member of this organization")

        membership = UserOrganization(
            user_id=user_id,
            organization_id=org_id,
            role=role
        )

        db.add(membership)
        await db.commit()
        await db.refresh(membership)

        # Load relationships
        await db.refresh(membership, ["user", "organization"])

        logger.info(f"User {user_id} added to org {org_id} with role {role}")
        return membership

    except Exception as e:
        logger.error(f"Failed to add organization member: {e}")
        await db.rollback()
        raise


async def remove_organization_member(
        db: AsyncSession,
        org_id: int,
        user_id: int
) -> bool:
    """Remove user from organization"""
    try:
        result = await db.execute(
            select(UserOrganization).filter(
                UserOrganization.organization_id == org_id,
                UserOrganization.user_id == user_id
            )
        )

        membership = result.scalars().first()
        if not membership:
            return False

        await db.delete(membership)
        await db.commit()

        logger.info(f"User {user_id} removed from org {org_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to remove organization member: {e}")
        await db.rollback()
        raise


async def get_organization_stats(db: AsyncSession, org_id: int) -> Dict[str, int]:
    """Get organization statistics"""
    try:
        # Member count
        member_count = await db.scalar(
            select(func.count(UserOrganization.id))
            .filter(UserOrganization.organization_id == org_id)
        )

        # Case count
        case_count = await db.scalar(
            select(func.count(Case.id))
            .filter(Case.organization_id == org_id)
        )

        return {
            "member_count": member_count or 0,
            "case_count": case_count or 0
        }

    except Exception as e:
        logger.error(f"Error getting organization stats: {e}")
        return {"member_count": 0, "case_count": 0}


async def update_user_role_in_organization(
        db: AsyncSession,
        org_id: int,
        user_id: int,
        new_role: UserRole
) -> Optional[UserOrganization]:
    """Update user's role in organization"""
    try:
        result = await db.execute(
            select(UserOrganization).filter(
                UserOrganization.organization_id == org_id,
                UserOrganization.user_id == user_id
            )
        )

        membership = result.scalars().first()
        if not membership:
            return None

        membership.role = new_role
        await db.commit()
        await db.refresh(membership)

        logger.info(f"Updated user {user_id} role to {new_role} in org {org_id}")
        return membership

    except Exception as e:
        logger.error(f"Failed to update user role: {e}")
        await db.rollback()
        raise