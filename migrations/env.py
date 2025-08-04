# migrations/env.py

import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import URL # Important for parsing the URL string
# Changed this import: We need the synchronous engine_from_config directly
# and then construct the AsyncEngine from its result.
from sqlalchemy.engine import engine_from_config as sync_engine_from_config
from sqlalchemy.ext.asyncio import AsyncEngine # Correct import for AsyncEngine

from alembic import context

# This is the path to your project's root, usually one level up from migrations/
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import your Base and models
from app.db.database import Base
from app.db.models import User, RefreshToken, BlacklistedToken

# New import for async handling
from asyncio import run as asyncio_run # Import asyncio.run


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline():
    """Run migrations in 'offline' mode.

    ... (unchanged) ...
    """
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise ValueError("sqlalchemy.url is not set in alembic.ini for offline mode.")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Get the URL from alembic.ini
    connectable_url = config.get_main_option("sqlalchemy.url")
    if not connectable_url:
        raise ValueError("sqlalchemy.url is not set in alembic.ini for online mode.")

    # Create a *synchronous* engine first from the config/URL
    # Then wrap it in AsyncEngine
    connectable_sync_engine = sync_engine_from_config(
        config.get_section(config.config_ini_section, {}), # Pass the whole section
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # Then create the AsyncEngine from the synchronous one
    connectable = AsyncEngine(connectable_sync_engine)


    async def run_async_migrations():
        async with connectable.begin() as conn: # Use begin() for transactional connection
            await conn.run_sync(
                lambda sync_conn: context.configure(
                    connection=sync_conn,
                    target_metadata=target_metadata,
                    # We already configured poolclass=pool.NullPool above
                    # dialect_opts={"paramstyle": "named"}, # This is typically dialect-specific and passed to engine_from_config
                )
            )
            await conn.run_sync(lambda sync_conn: context.run_migrations())

    # Run the entire async migration process
    asyncio_run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()