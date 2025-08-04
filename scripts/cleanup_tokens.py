"""
Token cleanup script for CHawk API
Run this periodically to clean expired tokens
"""
import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.db.database import AsyncSessionLocal
from app.db.crud.token import cleanup_expired_tokens
from loguru import logger

async def run_cleanup():
    """Run token cleanup process"""
    logger.info("🧹 Starting token cleanup process...")

    async with AsyncSessionLocal() as db:
        try:
            stats = await cleanup_expired_tokens(db)
            logger.info(f"✅ Token cleanup completed: {stats}")
            return stats
        except Exception as e:
            logger.error(f"❌ Token cleanup failed: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(run_cleanup())