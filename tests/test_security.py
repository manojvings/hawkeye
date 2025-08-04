"""
Security tests for CHawk API
"""
import pytest
from httpx import AsyncClient


class TestSecurityHeaders:
    """Test security headers"""

    async def test_security_headers_present(self, client: AsyncClient):
        """Test that security headers are present"""
        response = await client.get("/")

        headers = response.headers
        assert "x-content-type-options" in headers
        assert "x-frame-options" in headers
        assert "x-xss-protection" in headers
        assert "strict-transport-security" in headers

    async def test_trace_id_in_response(self, client: AsyncClient):
        """Test that trace ID is included in response headers"""
        response = await client.get("/")
        assert "x-trace-id" in response.headers


class TestPasswordComplexity:
    """Test password complexity validation"""

    @pytest.mark.parametrize("password,should_fail", [
        ("short", True),  # Too short
        ("nouppercase123!", True),  # No uppercase
        ("NOLOWERCASE123!", True),  # No lowercase
        ("NoNumbers!", True),  # No numbers
        ("NoSpecialChar123", True),  # No special characters
        ("ValidPassword123!", False),  # Valid password
    ])
    async def test_password_complexity(self, client: AsyncClient, password, should_fail):
        """Test various password complexity scenarios"""
        test_data = {
            "email": "passwordtest@example.com",
            "password": password,
            "password_confirm": password
        }

        response = await client.post("/api/v1/auth/register", json=test_data)

        if should_fail:
            assert response.status_code == 422
        else:
            assert response.status_code in [201, 409]  # 409 if user already exists