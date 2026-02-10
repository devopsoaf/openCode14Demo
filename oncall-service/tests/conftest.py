"""
Shared fixtures for oncall-service tests.

Uses httpx.ASGITransport so we never need a running server.
Database-hitting tests are marked with @pytest.mark.db and skipped
when no database is available (CI stage 5 supplies one).
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Provide a dummy DATABASE_URL for unit tests (DB is always mocked)
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

# Re-export helpers so tests can import from conftest or helpers
from helpers import FakeAsyncClient, FakeAsyncClientDown, fake_connection  # noqa: F401

# ---------------------------------------------------------------------------
# Ensure the app never tries to connect to a real DB during unit tests
# ---------------------------------------------------------------------------

_mock_pool = MagicMock()


@pytest.fixture(autouse=True)
def _patch_db_pool(request):
    """Patch the database pool for every test unless marked with @pytest.mark.db or @pytest.mark.integration."""
    markers = {m.name for m in request.node.iter_markers()}
    if "db" in markers or "integration" in markers:
        yield  # real DB
        return

    with (
        patch("app.database._connection_pool", _mock_pool),
        patch("app.database.get_pool", return_value=_mock_pool),
    ):
        yield


# ---------------------------------------------------------------------------
# Async client fixture (talks directly to the ASGI app)
# ---------------------------------------------------------------------------


@pytest.fixture()
async def client():
    """Async test client bound to the FastAPI app."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_schedule_payload():
    return {
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": "2026-01-01",
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
    }


@pytest.fixture()
def sample_escalate_payload():
    return {
        "incident_id": "inc-test-123",
        "team": "platform",
        "reason": "No acknowledgment within 5 minutes",
    }


@pytest.fixture()
def sample_policy_payload():
    return {
        "team": "platform",
        "levels": [
            {"level": 1, "wait_minutes": 5, "notify_target": "secondary"},
            {"level": 2, "wait_minutes": 10, "notify_target": "manager"},
        ],
    }
