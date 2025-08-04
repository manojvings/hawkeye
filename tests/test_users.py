"""
User endpoint tests for CHawk API
"""
import pytest
from httpx import AsyncClient


class TestUserProfile:
    """Test user profile functionality"""

    async def test_get_current_user_profile(self, client: AsyncClient, authenticated_user):
        """Test getting current user profile"""
        headers = {"Authorization": f"Bearer {authenticated_user['access_token']}"}

        response = await client.get("/api/v1/users/me", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == authenticated_user["user_data"]["email"]
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    async def test_get_profile_without_auth(self, client: AsyncClient):
        """Test getting profile without authentication"""
        response = await client.get("/api/v1/users/me")
        assert response.status_code == 401


class TestUserMetrics:
    """Test user metrics functionality"""

    async def test_get_app_metrics(self, client: AsyncClient, authenticated_user):
        """Test getting application metrics"""
        headers = {"Authorization": f"Bearer {authenticated_user['access_token']}"}

        response = await client.get("/api/v1/users/admin/metrics", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert "total_users" in data
        assert "active_users" in data
        assert "recent_registrations_24h" in data
        assert "active_refresh_tokens" in data
        assert "blacklisted_tokens" in data
        assert data["total_users"] >= 1  # At least the test user


class TestHealthCheck:
    """Test health check functionality"""

    async def test_health_check(self, client: AsyncClient):
        """Test application health check"""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert "trace_id" in data

    async def test_root_endpoint(self, client: AsyncClient):
        """Test root endpoint"""
        response = await client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "CHawk API" in data["message"]
        assert "version" in data


class TestRateLimiting:
    """Test rate limiting functionality"""

    async def test_rate_limiting_registration(self, client: AsyncClient):
        """Test rate limiting on registration endpoint"""
        test_data = {
            "email": "ratelimit@example.com",
            "password": "TestPassword123!",
            "password_confirm": "TestPassword123!"
        }

        # Make 6 requests quickly (limit is 5/minute)
        responses = []
        for i in range(6):
            test_data["email"] = f"ratelimit{i}@example.com"
            response = await client.post("/api/v1/auth/register", json=test_data)
            responses.append(response.status_code)

        # Should get rate limited on 6th request
        assert 429 in responses