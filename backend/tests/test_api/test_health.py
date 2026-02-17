"""Health check endpoint tests"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health check endpoint returns 200"""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ["healthy", "ok"]


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Test root endpoint is accessible"""
    response = await client.get("/")
    assert response.status_code == 200
