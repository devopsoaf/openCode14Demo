"""Integration tests for oncall-service.

These tests run against a REAL PostgreSQL database and the live ASGI app.
They require:
  - DATABASE_URL env var pointing to a running PostgreSQL instance
  - The database initialised with 01-init-database.sql (includes oncall schema + seed data)

Run with:
    pytest tests/integration/ -v -m integration
"""

import os
import uuid

import psycopg2
import pytest
from httpx import ASGITransport, AsyncClient

# Skip the entire module if no real database is available
DATABASE_URL = os.getenv("DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set -- skip integration tests"),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_conn():
    """Raw psycopg2 connection for verification queries."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture()
async def live_client():
    """Async client wired to the real FastAPI app (no DB mocks)."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Schedule CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_schedule(live_client, db_conn):
    """POST /api/v1/schedules stores the schedule in oncall.schedules."""
    team_name = f"integ-{uuid.uuid4().hex[:6]}"
    payload = {
        "team": team_name,
        "rotation_type": "weekly",
        "start_date": "2026-01-01",
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
    }

    resp = await live_client.post("/api/v1/schedules", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["team"] == team_name
    assert body["rotation_type"] == "weekly"
    assert len(body["engineers"]) == 2

    # Verify in database
    cur = db_conn.cursor()
    cur.execute("SELECT team, rotation_type FROM oncall.schedules WHERE team = %s", (team_name,))
    row = cur.fetchone()
    cur.close()

    assert row is not None
    assert row[0] == team_name
    assert row[1] == "weekly"


@pytest.mark.asyncio
async def test_list_schedules(live_client):
    """GET /api/v1/schedules returns the list (seed data has 3 teams)."""
    resp = await live_client.get("/api/v1/schedules")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert len(body["schedules"]) >= 1


@pytest.mark.asyncio
async def test_list_schedules_filter_by_team(live_client):
    """GET /api/v1/schedules?team=platform returns only platform schedules."""
    resp = await live_client.get("/api/v1/schedules?team=platform")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert all(s["team"] == "platform" for s in body["schedules"])


# ---------------------------------------------------------------------------
# Current on-call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_oncall(live_client):
    """GET /api/v1/oncall/current?team=platform returns current on-call engineers."""
    resp = await live_client.get("/api/v1/oncall/current?team=platform")
    assert resp.status_code == 200
    body = resp.json()
    assert body["team"] == "platform"
    assert body["primary"]["role"] == "primary"
    assert body["secondary"]["role"] == "secondary"
    assert body["escalation_minutes"] > 0


@pytest.mark.asyncio
async def test_get_current_oncall_not_found(live_client):
    """GET /api/v1/oncall/current?team=nonexistent returns 404."""
    resp = await live_client.get("/api/v1/oncall/current?team=nonexistent-team-xyz")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_escalate_incident(live_client, db_conn):
    """POST /api/v1/escalate creates escalation record."""
    payload = {
        "incident_id": f"inc-integ-{uuid.uuid4().hex[:8]}",
        "team": "platform",
        "reason": "Integration test escalation",
    }

    resp = await live_client.post("/api/v1/escalate", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["incident_id"] == payload["incident_id"]
    assert body["from_engineer"] != body["to_engineer"]

    # Verify in database
    cur = db_conn.cursor()
    cur.execute(
        "SELECT incident_id, from_engineer, to_engineer FROM oncall.escalations WHERE incident_id = %s",
        (payload["incident_id"],),
    )
    row = cur.fetchone()
    cur.close()

    assert row is not None
    assert row[0] == payload["incident_id"]


@pytest.mark.asyncio
async def test_escalate_no_schedule_returns_404(live_client):
    """POST /api/v1/escalate for nonexistent team returns 404."""
    payload = {
        "incident_id": f"inc-nosched-{uuid.uuid4().hex[:8]}",
        "team": "nonexistent-team-xyz",
    }
    resp = await live_client.post("/api/v1/escalate", json=payload)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_escalations(live_client):
    """GET /api/v1/escalations returns escalation history."""
    # First create an escalation
    payload = {
        "incident_id": f"inc-list-{uuid.uuid4().hex[:8]}",
        "team": "platform",
    }
    await live_client.post("/api/v1/escalate", json=payload)

    resp = await live_client.get("/api/v1/escalations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1


@pytest.mark.asyncio
async def test_list_escalations_filter_by_incident(live_client):
    """GET /api/v1/escalations?incident_id=... filters by incident."""
    incident_id = f"inc-filter-{uuid.uuid4().hex[:8]}"
    await live_client.post(
        "/api/v1/escalate",
        json={"incident_id": incident_id, "team": "platform"},
    )

    resp = await live_client.get(f"/api/v1/escalations?incident_id={incident_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert all(e["incident_id"] == incident_id for e in body["escalations"])


# ---------------------------------------------------------------------------
# Health & Metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_endpoint_with_real_db(live_client):
    """Health endpoint reports healthy when DB is reachable."""
    resp = await live_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["checks"]["database"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_with_real_db(live_client):
    """Readiness probe returns ready when DB is up."""
    resp = await live_client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_liveness(live_client):
    """Liveness probe always returns alive."""
    resp = await live_client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


@pytest.mark.asyncio
async def test_metrics_endpoint(live_client):
    """The /metrics endpoint returns Prometheus text format with custom metrics."""
    resp = await live_client.get("/metrics")
    assert resp.status_code == 200
    text = resp.text
    assert "escalations_total" in text
    assert "http_requests_total" in text or "http_request" in text


@pytest.mark.asyncio
async def test_post_schedule_validation_error(live_client):
    """Missing required fields returns 422."""
    resp = await live_client.post("/api/v1/schedules", json={"team": "x"})
    assert resp.status_code == 422
