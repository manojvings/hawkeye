import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete, and_, or_  # Removed text import
from loguru import logger

from app.db.models import RefreshToken, BlacklistedToken
from app.auth.security import Hasher


async def create_refresh_token_db(
        db: AsyncSession,
        user_id: int,
        token: str,
        expires_at: datetime
) -> RefreshToken:
    """
    Stores a hashed refresh token in the database.
    Enhanced with better error handling.
    """
    try:
        hashed_token = Hasher.hash_refresh_token(token)
        new_refresh_token = RefreshToken(
            user_id=user_id,
            token_hash=hashed_token,
            expires_at=expires_at
        )
        db.add(new_refresh_token)
        await db.commit()
        await db.refresh(new_refresh_token)
        logger.info(f"Refresh token created for user {user_id}")
        return new_refresh_token
    except Exception as e:
        logger.error(f"Failed to create refresh token for user {user_id}: {e}")
        await db.rollback()
        raise


async def get_refresh_token_by_hash(db: AsyncSession, token_hash: str) -> Optional[RefreshToken]:
    """
    Retrieves a refresh token record by its hash.
    Enhanced with logging.
    """
    try:
        result = await db.execute(
            select(RefreshToken).filter(
                and_(
                    RefreshToken.token_hash == token_hash,
                    RefreshToken.revoked_at.is_(None),
                    RefreshToken.expires_at > datetime.now(timezone.utc)
                )
            )
        )
        token = result.scalars().first()
        if token:
            logger.debug(f"Valid refresh token found for user {token.user_id}")
        return token
    except Exception as e:
        logger.error(f"Error retrieving refresh token: {e}")
        return None


async def revoke_refresh_token_db(db: AsyncSession, refresh_token_record: RefreshToken) -> RefreshToken:
    """
    Revokes a refresh token by setting its revoked_at timestamp.
    Enhanced with error handling.
    """
    try:
        refresh_token_record.revoked_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(refresh_token_record)
        logger.info(f"Refresh token revoked for user {refresh_token_record.user_id}")
        return refresh_token_record
    except Exception as e:
        logger.error(f"Failed to revoke refresh token: {e}")
        await db.rollback()
        raise


async def delete_expired_refresh_tokens(db: AsyncSession, batch_size: int = 1000) -> int:
    """
    Deletes refresh tokens that have expired or been revoked.
    Uses subquery approach for batch operations.
    Returns the number of deleted tokens.
    """
    try:
        total_deleted = 0

        while True:
            # Get IDs of tokens to delete in this batch
            subquery = (
                select(RefreshToken.id)
                .where(
                    or_(
                        RefreshToken.expires_at <= datetime.now(timezone.utc),
                        RefreshToken.revoked_at.isnot(None)
                    )
                )
                .limit(batch_size)
            )

            # Delete using the subquery
            result = await db.execute(
                delete(RefreshToken)
                .where(RefreshToken.id.in_(subquery))
            )

            deleted_count = result.rowcount
            total_deleted += deleted_count

            # Commit this batch
            await db.commit()

            logger.info(f"Deleted batch of {deleted_count} expired refresh tokens")

            # If we deleted less than batch_size, we're done
            if deleted_count < batch_size:
                break

            # Small delay between batches to prevent overwhelming the database
            if deleted_count == batch_size:  # Only sleep if there might be more batches
                await asyncio.sleep(0.1)

        logger.info(f"Total expired refresh tokens deleted: {total_deleted}")
        return total_deleted

    except Exception as e:
        logger.error(f"Failed to delete expired refresh tokens: {e}")
        await db.rollback()
        raise


async def add_to_blacklist(db: AsyncSession, jti: str, expires_at: datetime) -> BlacklistedToken:
    """
    Adds a JWT ID (jti) to the blacklist.
    Enhanced with error handling.
    """
    try:
        blacklisted_entry = BlacklistedToken(jti=jti, expires_at=expires_at)
        db.add(blacklisted_entry)
        await db.commit()
        await db.refresh(blacklisted_entry)
        logger.info(f"Token blacklisted: {jti}")
        return blacklisted_entry
    except Exception as e:
        logger.error(f"Failed to blacklist token {jti}: {e}")
        await db.rollback()
        raise


async def is_jti_blacklisted(db: AsyncSession, jti: str) -> bool:
    """
    Checks if a JWT ID (jti) is in the blacklist and is not expired.
    Enhanced with error handling.
    """
    try:
        result = await db.execute(
            select(BlacklistedToken).filter(
                and_(
                    BlacklistedToken.jti == jti,
                    BlacklistedToken.expires_at > datetime.now(timezone.utc)
                )
            )
        )
        is_blacklisted = result.scalars().first() is not None
        if is_blacklisted:
            logger.warning(f"Blacklisted token used: {jti}")
        return is_blacklisted
    except Exception as e:
        logger.error(f"Error checking blacklist for token {jti}: {e}")
        return False  # Fail open for availability


async def delete_expired_blacklisted_tokens(db: AsyncSession, batch_size: int = 1000) -> int:
    """
    Deletes blacklisted tokens that have expired.
    Uses subquery approach for batch operations.
    Returns the number of deleted tokens.
    """
    try:
        total_deleted = 0

        while True:
            # Get IDs of expired blacklisted tokens to delete in this batch
            subquery = (
                select(BlacklistedToken.id)
                .where(BlacklistedToken.expires_at <= datetime.now(timezone.utc))
                .limit(batch_size)
            )

            # Delete using the subquery
            result = await db.execute(
                delete(BlacklistedToken)
                .where(BlacklistedToken.id.in_(subquery))
            )

            deleted_count = result.rowcount
            total_deleted += deleted_count

            # Commit this batch
            await db.commit()

            logger.info(f"Deleted batch of {deleted_count} expired blacklisted tokens")

            # If we deleted less than batch_size, we're done
            if deleted_count < batch_size:
                break

            # Small delay between batches
            if deleted_count == batch_size:  # Only sleep if there might be more batches
                await asyncio.sleep(0.1)

        logger.info(f"Total expired blacklisted tokens deleted: {total_deleted}")
        return total_deleted

    except Exception as e:
        logger.error(f"Failed to delete expired blacklisted tokens: {e}")
        await db.rollback()
        raise


async def cleanup_expired_tokens(db: AsyncSession, batch_size: int = 1000) -> Dict[str, int]:
    """
    Cleanup all types of expired tokens using batch operations.
    Returns statistics of cleaned-up tokens.
    """
    stats = {
        "refresh_tokens_deleted": 0,
        "blacklisted_tokens_deleted": 0,
        "total_deleted": 0
    }

    try:
        # Clean up refresh tokens
        stats["refresh_tokens_deleted"] = await delete_expired_refresh_tokens(db, batch_size)

        # Clean up blocklisted tokens
        stats["blacklisted_tokens_deleted"] = await delete_expired_blacklisted_tokens(db, batch_size)

        stats["total_deleted"] = stats["refresh_tokens_deleted"] + stats["blacklisted_tokens_deleted"]

        logger.info(f"Token cleanup completed: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Token cleanup failed: {e}")
        raise