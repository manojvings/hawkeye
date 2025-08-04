"""
Authentication endpoint tests for CHawk API
"""
import pytest
from httpx import AsyncClient


class TestUserRegistration:
    """Test user registration functionality"""

    async def test_successful_registration(self, client: AsyncClient, test_user_data):
        """Test successful user registration"""
        response = await client.post("/api/v1/auth/register", json=test_user_data)

        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_duplicate_email_registration(self, client: AsyncClient, test_user_data):
        """Test registration with duplicate email"""
        # First registration
        response1 = await client.post("/api/v1/auth/register", json=test_user_data)
        assert response1.status_code == 201

        # Second registration with same email
        response2 = await client.post("/api/v1/auth/register", json=test_user_data)
        assert response2.status_code == 409
        assert "already exists" in response2.json()["detail"]

    async def test_weak_password_registration(self, client: AsyncClient):
        """Test registration with weak password"""
        weak_password_data = {
            "email": "test@example.com",
            "password": "weak",
            "password_confirm": "weak"
        }

        response = await client.post("/api/v1/auth/register", json=weak_password_data)
        assert response.status_code == 422

    async def test_password_mismatch_registration(self, client: AsyncClient):
        """Test registration with password mismatch"""
        mismatch_data = {
            "email": "test@example.com",
            "password": "StrongPassword123!",
            "password_confirm": "DifferentPassword123!"
        }

        response = await client.post("/api/v1/auth/register", json=mismatch_data)
        assert response.status_code == 422


class TestUserLogin:
    """Test user login functionality"""

    async def test_oauth2_login_success(self, client: AsyncClient, authenticated_user):
        """Test successful OAuth2 login"""
        login_data = {
            "username": authenticated_user["user_data"]["email"],
            "password": authenticated_user["user_data"]["password"]
        }

        response = await client.post(
            "/api/v1/auth/login",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_json_login_success(self, client: AsyncClient, authenticated_user):
        """Test successful JSON login"""
        login_data = {
            "username": authenticated_user["user_data"]["email"],
            "password": authenticated_user["user_data"]["password"]
        }

        response = await client.post("/api/v1/auth/login-json", json=login_data)

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_invalid_credentials_login(self, client: AsyncClient, authenticated_user):
        """Test login with invalid credentials"""
        login_data = {
            "username": authenticated_user["user_data"]["email"],
            "password": "WrongPassword123!"
        }

        response = await client.post("/api/v1/auth/login-json", json=login_data)
        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]


class TestTokenRefresh:
    """Test token refresh functionality"""

    async def test_successful_token_refresh(self, client: AsyncClient, authenticated_user):
        """Test successful token refresh"""
        response = await client.post(
            "/api/v1/auth/refresh-token",
            data={"refresh_token": authenticated_user["refresh_token"]},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["access_token"] != authenticated_user["access_token"]

    async def test_invalid_refresh_token(self, client: AsyncClient):
        """Test refresh with invalid token"""
        response = await client.post(
            "/api/v1/auth/refresh-token",
            data={"refresh_token": "invalid_token"},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 401


class TestLogout:
    """Test logout functionality"""

    async def test_successful_logout(self, client: AsyncClient, authenticated_user):
        """Test successful logout"""
        headers = {"Authorization": f"Bearer {authenticated_user['access_token']}"}

        response = await client.post("/api/v1/auth/logout", headers=headers)
        assert response.status_code == 204

    async def test_token_blacklisted_after_logout(self, client: AsyncClient, authenticated_user):
        """Test that token is blacklisted after logout"""
        headers = {"Authorization": f"Bearer {authenticated_user['access_token']}"}

        # Logout
        logout_response = await client.post("/api/v1/auth/logout", headers=headers)
        assert logout_response.status_code == 204

        # Try to use the same token
        profile_response = await client.get("/api/v1/users/me", headers=headers)
        assert profile_response.status_code == 401