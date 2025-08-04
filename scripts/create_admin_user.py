"""
Create admin user script for CHawk API
"""
import asyncio
import sys
from pathlib import Path
import getpass

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.db.database import AsyncSessionLocal
from app.db.crud.user import create_user_db, get_user_by_email
from app.auth.security import Hasher
from loguru import logger

async def create_admin_user():
    """Create admin user interactively"""
    logger.info("👤 Creating admin user for CHawk API...")

    # Get user input
    email = input("Enter admin email: ").strip()
    if not email:
        logger.error("Email is required")
        return

    password = getpass.getpass("Enter admin password: ")
    if not password:
        logger.error("Password is required")
        return

    password_confirm = getpass.getpass("Confirm password: ")
    if password != password_confirm:
        logger.error("Passwords don't match")
        return

    async with AsyncSessionLocal() as db:
        try:
            # Check if user already exists
            existing_user = await get_user_by_email(db, email)
            if existing_user:
                logger.warning(f"User {email} already exists")
                return

            # Create user
            hashed_password = Hasher.get_password_hash(password)
            user_data = {
                "email": email,
                "hashed_password": hashed_password,
                "is_active": True
            }

            user = await create_user_db(db, user_data)
            logger.info(f"✅ Admin user created: {user.email} (ID: {user.id})")

        except Exception as e:
            logger.error(f"❌ Failed to create admin user: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(create_admin_user())