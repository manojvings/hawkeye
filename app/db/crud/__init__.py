"""CRUD operations for database models"""
from .user import (
    get_user_by_email,
    get_user_by_id,
    create_user_db,
    update_user_db,
    delete_user_db,
    get_user_count,
    get_active_user_count,
    search_users_by_email
)
from .token import (
    create_refresh_token_db,
    get_refresh_token_by_hash,
    revoke_refresh_token_db,
    delete_expired_refresh_tokens,
    add_to_blacklist,
    is_jti_blacklisted,
    delete_expired_blacklisted_tokens,
    cleanup_expired_tokens
)

__all__ = [
    # User CRUD
    "get_user_by_email",
    "get_user_by_id",
    "create_user_db",
    "update_user_db",
    "delete_user_db",
    "get_user_count",
    "get_active_user_count",
    "search_users_by_email",
    # Token CRUD
    "create_refresh_token_db",
    "get_refresh_token_by_hash",
    "revoke_refresh_token_db",
    "delete_expired_refresh_tokens",
    "add_to_blacklist",
    "is_jti_blacklisted",
    "delete_expired_blacklisted_tokens",
    "cleanup_expired_tokens"
]