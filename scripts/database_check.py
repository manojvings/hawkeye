"""
Database connectivity and health check script
"""
import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.db.database import AsyncSessionLocal, engine
from app.db.models import User, RefreshToken, BlacklistedToken
from sqlalchemy import text
from loguru import logger

async def check_database():
    """Check database connectivity and table status"""
    logger.info("🔍 Checking database connectivity...")

    try:
        # Test basic connectivity
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("SELECT 1"))
            logger.info("✅ Database connection successful")

            # Check table counts
            user_count = await db.execute(text("SELECT COUNT(*) FROM users"))
            token_count = await db.execute(text("SELECT COUNT(*) FROM refresh_tokens"))
            blacklist_count = await db.execute(text("SELECT COUNT(*) FROM blacklisted_tokens"))

            logger.info(f"📊 Database statistics:")
            logger.info(f"   Users: {user_count.scalar()}")
            logger.info(f"   Refresh tokens: {token_count.scalar()}")
            logger.info(f"   Blacklisted tokens: {blacklist_count.scalar()}")

    except Exception as e:
        logger.error(f"❌ Database check failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(check_database())