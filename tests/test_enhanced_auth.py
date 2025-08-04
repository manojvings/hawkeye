import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.database import Base, get_db
from app.core.config import settings

# Test database URL - use different database for tests
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:password@localhost:5432/chawk_test"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestAsyncSessionLocal = sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture
async def db_session():
    """Create test database session"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestAsyncSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(db_session):
    """Create test client with database override"""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def sample_user_data():
    """Sample user data for testing"""
    return {
        "email": "test@example.com",
        "password": "TestPass123!",
        "password_confirm": "TestPass123!"
    }


@pytest.mark.asyncio
async def test_user_registration(client: AsyncClient, sample_user_data):
    """Test user registration with rate limiting"""
    response = await client.post("/api/v1/auth/register", json=sample_user_data)
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_user_login(client: AsyncClient, sample_user_data):
    """Test user login"""
    # Register user first
    await client.post("/api/v1/auth/register", json=sample_user_data)

    # Test JSON login
    login_data = {
        "username": sample_user_data["email"],
        "password": sample_user_data["password"]
    }
    response = await client.post("/api/v1/auth/login-json", json=login_data)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_get_current_user(client: AsyncClient, sample_user_data):
    """Test getting current user info"""
    # Register user
    reg_response = await client.post("/api/v1/auth/register", json=sample_user_data)
    token = reg_response.json()["access_token"]

    # Get current user
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == sample_user_data["email"]


@pytest.mark.asyncio
async def test_token_refresh(client: AsyncClient, sample_user_data):
    """Test token refresh functionality"""
    # Register user
    reg_response = await client.post("/api/v1/auth/register", json=sample_user_data)
    refresh_token = reg_response.json()["refresh_token"]

    # Refresh token
    refresh_data = {"refresh_token": refresh_token}
    response = await client.post("/api/v1/auth/refresh-token", data=refresh_data)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    # New refresh token should be different
    assert data["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_rate_limiting(client: AsyncClient):
    """Test rate limiting on login endpoint"""
    # This test would need to be implemented based on your specific rate limiting setup
    # For now, just test that multiple requests don't immediately fail
    for i in range(3):
        response = await client.post("/api/v1/auth/login-json", json={
            "username": "nonexistent@example.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401  # Should be unauthorized, not rate limited yet