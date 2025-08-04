# app/api/v1/endpoints/organizations.py
"""
Organization management endpoints with multi-tenant security
Following the established patterns from users_enhanced.py
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from typing import List, Optional
from uuid import UUID

from app.db.database import get_db
from app.db.crud.organization import (
    get_organization_by_uuid,
    get_organization_by_name,
    get_user_organizations,
    verify_organization_access,
    create_organization,
    update_organization,
    add_organization_member,
    remove_organization_member,
    get_organization_stats,
    update_user_role_in_organization
)
from app.db.crud.user import get_user_by_email, get_user_by_id
from app.api.v1.schemas.organizations import (
    OrganizationResponse,
    OrganizationCreate,
    OrganizationUpdate,
    AddOrganizationMember,
    UserOrganizationResponse,
    OrganizationWithRole
)
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


@router.get("/", response_model=PaginatedResponse[OrganizationWithRole])
@APIManagement.rate_limit(operation_type="read")
async def list_user_organizations(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        pagination: PaginationParams = Depends(get_pagination)
):
    """
    List all organizations the current user belongs to.

    Base features working automatically:
    - ✅ Audit Trail: This request is logged automatically
    - ✅ Rate Limiting: 100/min for read operations
    - ✅ Compression: Response will be compressed if > 1KB
    - ✅ Tracing: Full request correlation
    - ✅ UUID Security: All IDs exposed as UUIDs
    """
    # Get user's organizations
    user_orgs = await get_user_organizations(
        db,
        current_user.id,
        skip=pagination.offset,
        limit=pagination.size
    )

    # Get total count
    total = len(await get_user_organizations(db, current_user.id, skip=0, limit=1000))

    # Convert to response format with stats
    items = []
    for user_org in user_orgs:
        stats = await get_organization_stats(db, user_org.organization.id)
        org_with_role = OrganizationWithRole.from_user_org(
            user_org,
            member_count=stats["member_count"],
            case_count=stats["case_count"]
        )
        items.append(org_with_role)

    # Build response
    pages = (total + pagination.size - 1) // pagination.size

    return PaginatedResponse(
        items=items,
        total=total,
        page=pagination.page,
        size=pagination.size,
        pages=pages,
        has_next=pagination.page < pages,
        has_prev=pagination.page > 1
    )


@router.post("/", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
@APIManagement.rate_limit(operation_type="write")
async def create_new_organization(
        request: Request,
        org_data: OrganizationCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Create a new organization. Creator becomes org admin.

    Base features:
    - ✅ Rate Limiting: 30/min for write operations
    - ✅ Audit Trail: Organization creation is logged
    - ✅ UUID Security: Returns UUID for the new organization
    """
    # Check if organization name already exists
    existing = await get_organization_by_name(db, org_data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization with this name already exists"
        )

    # Create organization
    org = await create_organization(db, org_data, current_user.id)

    tracing.info(
        f"Organization created",
        org_name=org.name,
        org_uuid=str(org.uuid),
        creator=current_user.email
    )

    return OrganizationResponse.from_model(org, member_count=1, case_count=0)


@router.get("/{org_uuid}", response_model=OrganizationResponse)
@APIManagement.rate_limit(operation_type="read")
async def get_organization_details(
        request: Request,
        org_uuid: UUID,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Get organization details by UUID.

    Requires membership in the organization.
    """
    # Verify user has access
    membership = await verify_organization_access(db, current_user.id, org_uuid)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to organization"
        )

    org = membership.organization
    stats = await get_organization_stats(db, org.id)

    return OrganizationResponse.from_model(
        org,
        member_count=stats["member_count"],
        case_count=stats["case_count"]
    )


@router.patch("/{org_uuid}", response_model=OrganizationResponse)
@APIManagement.rate_limit(operation_type="write")
async def update_organization_details(
        request: Request,
        org_uuid: UUID,
        updates: OrganizationUpdate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Update organization details.

    Requires org_admin or admin role.
    """
    # Verify user has admin access
    membership = await verify_organization_access(
        db,
        current_user.id,
        org_uuid,
        required_roles=[UserRole.ADMIN, UserRole.ORG_ADMIN]
    )

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to update organization"
        )

    # Update organization
    org = await update_organization(db, membership.organization, updates)
    stats = await get_organization_stats(db, org.id)

    tracing.info(
        f"Organization updated",
        org_uuid=str(org.uuid),
        updated_by=current_user.email
    )

    return OrganizationResponse.from_model(
        org,
        member_count=stats["member_count"],
        case_count=stats["case_count"]
    )


@router.get("/{org_uuid}/members", response_model=List[UserOrganizationResponse])
@APIManagement.rate_limit(operation_type="read")
async def list_organization_members(
        request: Request,
        org_uuid: UUID,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    List organization members.

    Requires membership in the organization.
    """
    # Verify user has access
    membership = await verify_organization_access(db, current_user.id, org_uuid)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to organization"
        )

    # Get all members
    from sqlalchemy import select
    from app.db.models import UserOrganization

    result = await db.execute(
        select(UserOrganization)
        .options(
            selectinload(UserOrganization.user),
            selectinload(UserOrganization.organization)
        )
        .filter(UserOrganization.organization_id == membership.organization.id)
    )

    members = result.scalars().all()

    return [UserOrganizationResponse.from_model(m) for m in members]


@router.post("/{org_uuid}/members", response_model=UserOrganizationResponse)
@APIManagement.rate_limit(operation_type="write")
async def add_member_to_organization(
        request: Request,
        org_uuid: UUID,
        member_data: AddOrganizationMember,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Add a member to the organization.

    Requires org_admin or admin role.
    """
    # Verify user has admin access
    membership = await verify_organization_access(
        db,
        current_user.id,
        org_uuid,
        required_roles=[UserRole.ADMIN, UserRole.ORG_ADMIN]
    )

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to add members"
        )

    # Find user to add
    user_to_add = await get_user_by_email(db, member_data.user_email)
    if not user_to_add:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Add member
    try:
        new_membership = await add_organization_member(
            db,
            membership.organization.id,
            user_to_add.id,
            member_data.role
        )

        tracing.info(
            f"Member added to organization",
            org_uuid=str(org_uuid),
            added_user=member_data.user_email,
            role=member_data.role.value,
            added_by=current_user.email
        )

        return UserOrganizationResponse.from_model(new_membership)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.delete("/{org_uuid}/members/{user_uuid}", status_code=status.HTTP_204_NO_CONTENT)
@APIManagement.rate_limit(operation_type="delete")
async def remove_member_from_organization(
        request: Request,
        org_uuid: UUID,
        user_uuid: UUID,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Remove a member from the organization.

    Requires org_admin or admin role.
    Users can also remove themselves.
    """
    # Get user to remove
    from sqlalchemy import select
    from app.db.models import User as UserModel

    result = await db.execute(
        select(UserModel).filter(UserModel.uuid == user_uuid)
    )
    user_to_remove = result.scalars().first()

    if not user_to_remove:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Check if user is removing themselves
    is_self_remove = user_to_remove.id == current_user.id

    # Verify permissions
    membership = await verify_organization_access(db, current_user.id, org_uuid)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to organization"
        )

    # If not self-remove, require admin permissions
    if not is_self_remove and membership.role not in [UserRole.ADMIN, UserRole.ORG_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to remove members"
        )

    # Remove member
    success = await remove_organization_member(
        db,
        membership.organization.id,
        user_to_remove.id
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in organization"
        )

    tracing.info(
        f"Member removed from organization",
        org_uuid=str(org_uuid),
        removed_user=user_to_remove.email,
        removed_by=current_user.email,
        self_remove=is_self_remove
    )


@router.patch("/{org_uuid}/members/{user_uuid}/role", response_model=UserOrganizationResponse)
@APIManagement.rate_limit(operation_type="write")
async def update_member_role(
        request: Request,
        org_uuid: UUID,
        user_uuid: UUID,
        role_update: dict,  # {"role": "analyst"}
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Update a member's role in the organization.

    Requires org_admin or admin role.
    """
    # Validate role
    try:
        new_role = UserRole(role_update.get("role"))
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid role specified"
        )

    # Verify user has admin access
    membership = await verify_organization_access(
        db,
        current_user.id,
        org_uuid,
        required_roles=[UserRole.ADMIN, UserRole.ORG_ADMIN]
    )

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to update member roles"
        )

    # Get user to update
    from sqlalchemy import select
    from app.db.models import User as UserModel

    result = await db.execute(
        select(UserModel).filter(UserModel.uuid == user_uuid)
    )
    user_to_update = result.scalars().first()

    if not user_to_update:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Update role
    updated_membership = await update_user_role_in_organization(
        db,
        membership.organization.id,
        user_to_update.id,
        new_role
    )

    if not updated_membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in organization"
        )

    # Reload relationships for response
    await db.refresh(updated_membership, ["user", "organization"])

    tracing.info(
        f"Member role updated",
        org_uuid=str(org_uuid),
        updated_user=user_to_update.email,
        new_role=new_role.value,
        updated_by=current_user.email
    )

    return UserOrganizationResponse.from_model(updated_membership)