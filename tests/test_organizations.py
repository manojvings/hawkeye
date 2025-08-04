# tests/test_organizations.py
import pytest
from httpx import AsyncClient
from uuid import uuid4
from app.main import app
from app.db.database import get_db
from tests.conftest import override_get_db, create_test_user, get_auth_headers


@pytest.mark.asyncio
async def test_create_organization_with_uuid_security(client: AsyncClient):
    """Test organization creation returns UUID"""
    # Create user and authenticate
    user = await create_test_user()
    headers = await get_auth_headers(user.email, "testpassword123")

    # Create organization
    org_data = {
        "name": "Test Security Org",
        "description": "Test organization for security testing"
    }

    response = await client.post(
        "/api/v1/organizations",
        json=org_data,
        headers=headers
    )

    assert response.status_code == 201
    data = response.json()

    # Verify UUID is returned
    assert "id" in data
    assert len(data["id"]) == 36  # UUID length
    assert "-" in data["id"]  # UUID format

    # Verify other fields
    assert data["name"] == org_data["name"]
    assert data["description"] == org_data["description"]
    assert data["is_active"] is True
    assert data["member_count"] == 1  # Creator is automatically added


@pytest.mark.asyncio
async def test_organization_enumeration_protection(client: AsyncClient):
    """Test UUID prevents enumeration attacks"""
    user = await create_test_user()
    headers = await get_auth_headers(user.email, "testpassword123")

    # Try to access with integer ID
    response = await client.get("/api/v1/organizations/1", headers=headers)
    assert response.status_code == 422  # Validation error

    # Try to access with invalid UUID
    response = await client.get("/api/v1/organizations/invalid-uuid", headers=headers)
    assert response.status_code == 422  # Validation error

    # Try to access with valid but non-existent UUID
    fake_uuid = str(uuid4())
    response = await client.get(f"/api/v1/organizations/{fake_uuid}", headers=headers)
    assert response.status_code == 403  # Access denied (not 404 to avoid information leakage)


@pytest.mark.asyncio
async def test_multi_tenant_isolation(client: AsyncClient):
    """Test users can only see their organization's data"""
    # Create two users
    user1 = await create_test_user(email="user1@test.com")
    user2 = await create_test_user(email="user2@test.com")

    headers1 = await get_auth_headers(user1.email, "testpassword123")
    headers2 = await get_auth_headers(user2.email, "testpassword123")

    # User1 creates org1
    org1_response = await client.post(
        "/api/v1/organizations",
        json={"name": "Org1", "description": "User1's org"},
        headers=headers1
    )
    assert org1_response.status_code == 201
    org1_uuid = org1_response.json()["id"]

    # User2 creates org2
    org2_response = await client.post(
        "/api/v1/organizations",
        json={"name": "Org2", "description": "User2's org"},
        headers=headers2
    )
    assert org2_response.status_code == 201
    org2_uuid = org2_response.json()["id"]

    # User1 should not be able to access org2
    response = await client.get(f"/api/v1/organizations/{org2_uuid}", headers=headers1)
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]

    # User2 should not be able to access org1
    response = await client.get(f"/api/v1/organizations/{org1_uuid}", headers=headers2)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_add_remove_organization_members(client: AsyncClient):
    """Test adding and removing organization members"""
    # Create org admin and regular user
    admin = await create_test_user(email="admin@test.com")
    user = await create_test_user(email="user@test.com")

    admin_headers = await get_auth_headers(admin.email, "testpassword123")
    user_headers = await get_auth_headers(user.email, "testpassword123")

    # Admin creates organization
    org_response = await client.post(
        "/api/v1/organizations",
        json={"name": "Test Org", "description": "Test"},
        headers=admin_headers
    )
    org_uuid = org_response.json()["id"]

    # Admin adds user as analyst
    add_response = await client.post(
        f"/api/v1/organizations/{org_uuid}/members",
        json={"user_email": user.email, "role": "analyst"},
        headers=admin_headers
    )
    assert add_response.status_code == 200
    assert add_response.json()["user_email"] == user.email
    assert add_response.json()["role"] == "analyst"

    # User can now access the organization
    access_response = await client.get(
        f"/api/v1/organizations/{org_uuid}",
        headers=user_headers
    )
    assert access_response.status_code == 200

    # Regular user cannot add members
    add_fail_response = await client.post(
        f"/api/v1/organizations/{org_uuid}/members",
        json={"user_email": "another@test.com", "role": "analyst"},
        headers=user_headers
    )
    assert add_fail_response.status_code == 403

    # Get user UUID for removal
    members_response = await client.get(
        f"/api/v1/organizations/{org_uuid}/members",
        headers=admin_headers
    )
    user_uuid = None
    for member in members_response.json():
        if member["user_email"] == user.email:
            user_uuid = member["user_id"]
            break

    # Admin removes user
    remove_response = await client.delete(
        f"/api/v1/organizations/{org_uuid}/members/{user_uuid}",
        headers=admin_headers
    )
    assert remove_response.status_code == 204

    # User can no longer access
    no_access_response = await client.get(
        f"/api/v1/organizations/{org_uuid}",
        headers=user_headers
    )
    assert no_access_response.status_code == 403


@pytest.mark.asyncio
async def test_organization_role_permissions(client: AsyncClient):
    """Test different role permissions in organizations"""
    # Create users
    org_admin = await create_test_user(email="orgadmin@test.com")
    analyst = await create_test_user(email="analyst@test.com")
    readonly = await create_test_user(email="readonly@test.com")

    org_admin_headers = await get_auth_headers(org_admin.email, "testpassword123")

    # Create organization
    org_response = await client.post(
        "/api/v1/organizations",
        json={"name": "Role Test Org", "description": "Testing roles"},
        headers=org_admin_headers
    )
    org_uuid = org_response.json()["id"]

    # Add users with different roles
    await client.post(
        f"/api/v1/organizations/{org_uuid}/members",
        json={"user_email": analyst.email, "role": "analyst"},
        headers=org_admin_headers
    )

    await client.post(
        f"/api/v1/organizations/{org_uuid}/members",
        json={"user_email": readonly.email, "role": "read_only"},
        headers=org_admin_headers
    )

    # Test analyst can read but not admin
    analyst_headers = await get_auth_headers(analyst.email, "testpassword123")

    # Analyst can read
    read_response = await client.get(
        f"/api/v1/organizations/{org_uuid}",
        headers=analyst_headers
    )
    assert read_response.status_code == 200

    # Analyst cannot update
    update_response = await client.patch(
        f"/api/v1/organizations/{org_uuid}",
        json={"description": "Updated by analyst"},
        headers=analyst_headers
    )
    assert update_response.status_code == 403

    # Read-only user can only read
    readonly_headers = await get_auth_headers(readonly.email, "testpassword123")

    read_response = await client.get(
        f"/api/v1/organizations/{org_uuid}",
        headers=readonly_headers
    )
    assert read_response.status_code == 200


@pytest.mark.asyncio
async def test_organization_self_removal(client: AsyncClient):
    """Test users can remove themselves from organizations"""
    # Create org admin and user
    admin = await create_test_user(email="admin@test.com")
    user = await create_test_user(email="user@test.com")

    admin_headers = await get_auth_headers(admin.email, "testpassword123")
    user_headers = await get_auth_headers(user.email, "testpassword123")

    # Create org and add user
    org_response = await client.post(
        "/api/v1/organizations",
        json={"name": "Self Remove Test", "description": "Test"},
        headers=admin_headers
    )
    org_uuid = org_response.json()["id"]

    await client.post(
        f"/api/v1/organizations/{org_uuid}/members",
        json={"user_email": user.email, "role": "analyst"},
        headers=admin_headers
    )

    # Get user's UUID
    members_response = await client.get(
        f"/api/v1/organizations/{org_uuid}/members",
        headers=user_headers
    )
    user_uuid = None
    for member in members_response.json():
        if member["user_email"] == user.email:
            user_uuid = member["user_id"]
            break

    # User removes themselves
    remove_response = await client.delete(
        f"/api/v1/organizations/{org_uuid}/members/{user_uuid}",
        headers=user_headers
    )
    assert remove_response.status_code == 204

    # Verify user no longer has access
    no_access_response = await client.get(
        f"/api/v1/organizations/{org_uuid}",
        headers=user_headers
    )
    assert no_access_response.status_code == 403