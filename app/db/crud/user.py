from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import Optional, Dict, Any, List
from loguru import logger

from app.db.models import User


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """
    Asynchronously retrieves a user by their email address.
    Enhanced with error handling.
    """
    try:
        result = await db.execute(select(User).filter(User.email == email))
        user = result.scalars().first()
        if user:
            logger.debug(f"User found: {email}")
        return user
    except Exception as e:
        logger.error(f"Error retrieving user by email {email}: {e}")
        return None


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    """
    Asynchronously retrieves a user by their ID.
    Enhanced with error handling.
    """
    try:
        result = await db.execute(select(User).filter(User.id == user_id))
        user = result.scalars().first()
        if user:
            logger.debug(f"User found: ID {user_id}")
        return user
    except Exception as e:
        logger.error(f"Error retrieving user by ID {user_id}: {e}")
        return None


async def create_user_db(db: AsyncSession, user_data: Dict[str, Any]) -> User:
    """
    Asynchronously creates a new user record in the database.
    Enhanced with validation and error handling.
    """
    try:
        # Validate required fields
        if not user_data.get('email') or not user_data.get('hashed_password'):
            raise ValueError("Email and hashed_password are required")

        user = User(**user_data)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(f"User created successfully: {user.email}")
        return user
    except Exception as e:
        logger.error(f"Failed to create user: {e}")
        await db.rollback()
        raise


async def update_user_db(db: AsyncSession, user: User, updates: Dict[str, Any]) -> User:
    """
    Asynchronously updates an existing user record in the database.
    Enhanced with validation and error handling.
    """
    try:
        # Prevent updating sensitive fields without proper validation
        protected_fields = {'id', 'created_at'}
        for field in protected_fields:
            if field in updates:
                logger.warning(f"Attempt to update protected field: {field}")
                updates.pop(field)

        for key, value in updates.items():
            if hasattr(user, key):
                setattr(user, key, value)
            else:
                logger.warning(f"Attempt to update non-existent field: {key}")

        await db.commit()
        await db.refresh(user)
        logger.info(f"User updated successfully: {user.email}")
        return user
    except Exception as e:
        logger.error(f"Failed to update user {user.email}: {e}")
        await db.rollback()
        raise


async def delete_user_db(db: AsyncSession, user: User) -> None:
    """
    Asynchronously deletes a user record from the database.
    Enhanced with proper cascade handling and error handling.
    """
    try:
        # Note: This will cascade delete related records due to SQLAlchemy relationships
        await db.delete(user)  # Fixed: removed duplicate db.delete
        await db.commit()
        logger.info(f"User deleted successfully: {user.email}")
    except Exception as e:
        logger.error(f"Failed to delete user {user.email}: {e}")
        await db.rollback()
        raise


async def get_user_count(db: AsyncSession) -> int:
    """
    Get total count of users in the database.
    """
    try:
        result = await db.execute(select(func.count(User.id)))
        count = result.scalar() or 0
        return count
    except Exception as e:
        logger.error(f"Error getting user count: {e}")
        return 0


async def get_active_user_count(db: AsyncSession) -> int:
    """
    Get count of active users in the database.
    """
    try:
        result = await db.execute(
            select(func.count(User.id)).where(User.is_active == True)
        )
        count = result.scalar() or 0
        return count
    except Exception as e:
        logger.error(f"Error getting active user count: {e}")
        return 0


async def search_users_by_email(db: AsyncSession, email_pattern: str, limit: int = 50) -> List[User]:
    """
    Search users by email pattern (for admin purposes).
    """
    try:
        result = await db.execute(
            select(User)
            .filter(User.email.like(f"%{email_pattern}%"))
            .limit(limit)
        )
        users = result.scalars().all()
        logger.info(f"Found {len(users)} users matching pattern: {email_pattern}")
        return list(users)
    except Exception as e:
        logger.error(f"Error searching users: {e}")
        return []


async def is_user_in_organization(db: AsyncSession, user_id: int, organization_id: int) -> bool:
    """Check if a user belongs to a specific organization"""
    try:
        from app.db.models import UserOrganization
        result = await db.execute(
            select(UserOrganization).filter(
                UserOrganization.user_id == user_id,
                UserOrganization.organization_id == organization_id
            )
        )
        return result.scalars().first() is not None
    except Exception as e:
        logger.error(f"Error checking user organization membership: {e}")
        return False