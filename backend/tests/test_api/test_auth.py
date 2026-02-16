"""Authentication API tests"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User


@pytest.mark.asyncio
class TestUserRegistration:
    """Test user registration flows"""

    async def test_register_new_user(self, client: AsyncClient, db_session: AsyncSession):
        """Test successful user registration"""
        user_data = {
            "email": "newuser@example.com",
            "password": "securepass123"
        }

        response = await client.post("/api/v1/auth/register", json=user_data)

        assert response.status_code == 201
        data = response.json()

        # Should return tokens since DOUBLE_CHECK_ENABLED is false in test env
        assert "access_token" in data
        assert "refresh_token" in data

        # Verify user was created in database
        result = await db_session.execute(
            select(User).where(User.email == user_data["email"])
        )
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.email == user_data["email"]

        # Cleanup
        await db_session.delete(user)
        await db_session.commit()

    async def test_register_duplicate_email(self, client: AsyncClient, test_user):
        """Test registration with existing email fails"""
        user_data = {
            "email": test_user.email,
            "password": "anotherpass123"
        }

        response = await client.post("/api/v1/auth/register", json=user_data)

        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()

    async def test_register_invalid_email(self, client: AsyncClient):
        """Test registration with invalid email format"""
        user_data = {
            "email": "not-an-email",
            "password": "securepass123"
        }

        response = await client.post("/api/v1/auth/register", json=user_data)

        assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
class TestUserLogin:
    """Test user login flows"""

    async def test_login_success(self, client: AsyncClient, test_user):
        """Test successful login"""
        credentials = {
            "email": test_user.email,
            "password": "testpass123"
        }

        response = await client.post("/api/v1/auth/login", json=credentials)

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_login_wrong_password(self, client: AsyncClient, test_user):
        """Test login with incorrect password"""
        credentials = {
            "email": test_user.email,
            "password": "wrongpassword"
        }

        response = await client.post("/api/v1/auth/login", json=credentials)

        assert response.status_code == 401
        assert "incorrect" in response.json()["detail"].lower()

    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Test login with non-existent email"""
        credentials = {
            "email": "nonexistent@example.com",
            "password": "somepassword"
        }

        response = await client.post("/api/v1/auth/login", json=credentials)

        assert response.status_code == 401


@pytest.mark.asyncio
class TestTokenRefresh:
    """Test token refresh functionality"""

    async def test_refresh_token_success(self, client: AsyncClient, test_user):
        """Test successful token refresh"""
        from app.core.security import create_refresh_token

        refresh_token = create_refresh_token({"sub": str(test_user.id)})

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_refresh_token_invalid(self, client: AsyncClient):
        """Test refresh with invalid token"""
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid.token.here"}
        )

        assert response.status_code == 401


@pytest.mark.asyncio
class TestAuthenticatedEndpoints:
    """Test endpoints requiring authentication"""

    async def test_get_current_user(self, client: AsyncClient, test_user, auth_headers):
        """Test getting current user info"""
        response = await client.get("/api/v1/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert data["status"] == "verified"

    async def test_get_current_user_unauthorized(self, client: AsyncClient):
        """Test getting current user without authentication"""
        response = await client.get("/api/v1/auth/me")

        assert response.status_code == 401
