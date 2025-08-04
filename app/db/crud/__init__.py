"""CRUD operations for database models"""
from .user import (
    get_user_by_email,
    get_user_by_id,
    create_user_db,
    update_user_db,
    delete_user_db,
    get_user_count,
    get_active_user_count,
    search_users_by_email,
    is_user_in_organization
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
from .organization import (
    get_organization_by_id,
    get_organization_by_uuid,
    create_organization,
    update_organization,
    delete_organization,
    get_user_organizations,
    add_user_to_organization,
    remove_user_from_organization
)
from . import case
from . import task
from . import observable
from . import alert

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