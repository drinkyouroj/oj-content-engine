"""
Tests for the FastAPI application and /health endpoint.

Uses mocked database and Redis connections to test without external deps.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from worker.app.main import app


@pytest.mark.asyncio
async def test_health_endpoint_healthy():
    """Health endpoint returns 200 with status 'healthy' when all services are up."""
    with (
        patch("worker.app.main.check_db", new_callable=AsyncMock, return_value=True),
        patch("worker.app.main.check_redis", new_callable=AsyncMock, return_value=True),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] is True
        assert data["redis"] is True


@pytest.mark.asyncio
async def test_health_endpoint_db_down():
    """Health endpoint returns 503 when database is unreachable."""
    with (
        patch("worker.app.main.check_db", new_callable=AsyncMock, return_value=False),
        patch("worker.app.main.check_redis", new_callable=AsyncMock, return_value=True),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] is False
