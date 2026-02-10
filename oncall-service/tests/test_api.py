"""Tests for the on-call API -- schedules CRUD, current on-call, escalation, policies, metrics."""

import json
import uuid
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest
from helpers import FakeAsyncClient, FakeAsyncClientDown, fake_connection, make_fake_async_client

# ── POST /api/v1/schedules -- create schedule ─────────────────


@pytest.mark.asyncio
async def test_create_schedule(client, sample_schedule_payload):
    """POST /api/v1/schedules creates a schedule and returns 201."""
    fake_row = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    with patch("app.routers.api.get_db_connection", fake_connection([fake_row])):
        resp = await client.post("/api/v1/schedules", json=sample_schedule_payload)

    assert resp.status_code == 201
    body = resp.json()
    assert body["team"] == "platform"
    assert body["rotation_type"] == "weekly"
    assert len(body["engineers"]) == 2


@pytest.mark.asyncio
async def test_create_schedule_validation_error(client):
    """POST /api/v1/schedules rejects empty engineers list."""
    payload = {
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": "2026-01-01",
        "engineers": [],
    }
    resp = await client.post("/api/v1/schedules", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_schedule_db_error(client, sample_schedule_payload):
    """POST /api/v1/schedules returns 500 on DB error."""
    with patch("app.routers.api.get_db_connection", side_effect=Exception("DB down")):
        resp = await client.post("/api/v1/schedules", json=sample_schedule_payload)
    assert resp.status_code == 500


# ── GET /api/v1/schedules -- list schedules ───────────────────


@pytest.mark.asyncio
async def test_list_schedules(client):
    """GET /api/v1/schedules returns schedule list."""
    fake_rows = [
        {
            "id": str(uuid.uuid4()),
            "team": "platform",
            "rotation_type": "weekly",
            "start_date": date(2026, 1, 1),
            "engineers": [{"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True}],
            "escalation_minutes": 5,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
    ]

    with patch("app.routers.api.get_db_connection", fake_connection([fake_rows])):
        resp = await client.get("/api/v1/schedules")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["schedules"][0]["team"] == "platform"


@pytest.mark.asyncio
async def test_list_schedules_with_team_filter(client):
    """GET /api/v1/schedules?team=backend filters by team."""
    fake_rows = [
        {
            "id": str(uuid.uuid4()),
            "team": "backend",
            "rotation_type": "weekly",
            "start_date": date(2026, 1, 1),
            "engineers": [{"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True}],
            "escalation_minutes": 10,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
    ]

    with patch("app.routers.api.get_db_connection", fake_connection([fake_rows])):
        resp = await client.get("/api/v1/schedules?team=backend")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["schedules"][0]["team"] == "backend"


@pytest.mark.asyncio
async def test_list_schedules_empty(client):
    """GET /api/v1/schedules returns empty list when none exist."""
    with patch("app.routers.api.get_db_connection", fake_connection([[]])):
        resp = await client.get("/api/v1/schedules")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["schedules"] == []


# ── GET /api/v1/oncall/current -- current on-call ─────────────


@pytest.mark.asyncio
async def test_get_current_oncall(client):
    """GET /api/v1/oncall/current?team=platform returns current on-call."""
    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    with patch("app.routers.api.get_db_connection", fake_connection([fake_schedule])):
        resp = await client.get("/api/v1/oncall/current?team=platform")

    assert resp.status_code == 200
    body = resp.json()
    assert body["team"] == "platform"
    assert body["primary"]["role"] == "primary"
    assert body["secondary"]["role"] == "secondary"
    assert body["escalation_minutes"] == 5


@pytest.mark.asyncio
async def test_get_current_oncall_missing_team(client):
    """GET /api/v1/oncall/current requires team query param."""
    resp = await client.get("/api/v1/oncall/current")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_current_oncall_no_schedule(client):
    """GET /api/v1/oncall/current returns 404 for unknown team."""
    with patch("app.routers.api.get_db_connection", fake_connection([None])):
        resp = await client.get("/api/v1/oncall/current?team=nonexistent")

    assert resp.status_code == 404


# ── POST /api/v1/escalate -- escalate incident ────────────────


@pytest.mark.asyncio
async def test_escalate_incident(client, sample_escalate_payload):
    """POST /api/v1/escalate creates escalation record."""
    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    # DB calls: 1) lookup schedule, 2) insert escalation, 3) deactivate timer,
    # 4) lookup policy for timer, 5) insert timer
    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_schedule, None, None, None, None]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/escalate", json=sample_escalate_payload)

    assert resp.status_code == 201
    body = resp.json()
    assert body["incident_id"] == "inc-test-123"
    assert "from_engineer" in body
    assert "to_engineer" in body
    assert body["from_engineer"] != body["to_engineer"]
    assert body["level"] == 1


@pytest.mark.asyncio
async def test_escalate_no_schedule(client, sample_escalate_payload):
    """POST /api/v1/escalate returns 404 when no schedule found."""
    with patch("app.routers.api.get_db_connection", fake_connection([None])):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/escalate", json=sample_escalate_payload)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_escalate_single_engineer(client):
    """POST /api/v1/escalate with single engineer escalates to manager."""
    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "solo",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_schedule, None, None, None, None]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post(
                "/api/v1/escalate",
                json={"incident_id": "inc-solo", "team": "solo"},
            )

    # Single-engineer teams now escalate to manager instead of returning 422
    assert resp.status_code == 201
    body = resp.json()
    assert body["to_engineer"] == "admin@expertmind.local"


# ── GET /api/v1/escalations -- list escalation history ────────


@pytest.mark.asyncio
async def test_list_escalations(client):
    """GET /api/v1/escalations returns escalation history."""
    fake_rows = [
        {
            "id": str(uuid.uuid4()),
            "incident_id": "inc-123",
            "from_engineer": "omarafidi2005@gmail.com",
            "to_engineer": "omarafidi2005@gmail.com",
            "level": 1,
            "reason": "Timeout",
            "escalated_at": datetime(2026, 2, 10, 12, 0, 0, tzinfo=timezone.utc),
        }
    ]

    with patch("app.routers.api.get_db_connection", fake_connection([fake_rows])):
        resp = await client.get("/api/v1/escalations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["escalations"][0]["incident_id"] == "inc-123"
    assert body["escalations"][0]["level"] == 1


# ── POST /api/v1/escalation-policies -- create policy ────────


@pytest.mark.asyncio
async def test_create_escalation_policy(client):
    """POST /api/v1/escalation-policies creates a policy."""
    payload = {
        "team": "platform",
        "levels": [
            {"level": 1, "wait_minutes": 5, "notify_target": "secondary"},
            {"level": 2, "wait_minutes": 10, "notify_target": "manager"},
        ],
    }

    with patch("app.routers.api.get_db_connection", fake_connection([None, None, None])):
        resp = await client.post("/api/v1/escalation-policies", json=payload)

    assert resp.status_code == 201
    body = resp.json()
    assert body["team"] == "platform"
    assert len(body["levels"]) == 2
    assert body["levels"][0]["wait_minutes"] == 5


@pytest.mark.asyncio
async def test_create_escalation_policy_validation_error(client):
    """POST /api/v1/escalation-policies rejects empty levels."""
    payload = {"team": "platform", "levels": []}
    resp = await client.post("/api/v1/escalation-policies", json=payload)
    assert resp.status_code == 422


# ── GET /api/v1/escalation-policies -- list policies ─────────


@pytest.mark.asyncio
async def test_list_escalation_policies(client):
    """GET /api/v1/escalation-policies returns policy list."""
    fake_rows = [
        {
            "team": "platform",
            "level": 1,
            "wait_minutes": 5,
            "notify_target": "secondary",
        },
        {
            "team": "platform",
            "level": 2,
            "wait_minutes": 10,
            "notify_target": "manager",
        },
    ]

    with patch("app.routers.api.get_db_connection", fake_connection([fake_rows])):
        resp = await client.get("/api/v1/escalation-policies")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["policies"][0]["levels"]) == 2


# ── GET /api/v1/escalation-policies/{team} -- get policy ─────


@pytest.mark.asyncio
async def test_get_escalation_policy(client):
    """GET /api/v1/escalation-policies/platform returns the team policy."""
    fake_rows = [
        {
            "team": "platform",
            "level": 1,
            "wait_minutes": 5,
            "notify_target": "secondary",
        },
    ]

    with patch("app.routers.api.get_db_connection", fake_connection([fake_rows])):
        resp = await client.get("/api/v1/escalation-policies/platform")

    assert resp.status_code == 200
    body = resp.json()
    assert body["team"] == "platform"


@pytest.mark.asyncio
async def test_get_escalation_policy_not_found(client):
    """GET /api/v1/escalation-policies/nonexistent returns 404."""
    with patch("app.routers.api.get_db_connection", fake_connection([[]])):
        resp = await client.get("/api/v1/escalation-policies/nonexistent")

    assert resp.status_code == 404


# ── POST /api/v1/check-escalations -- auto escalation ────────


@pytest.mark.asyncio
async def test_check_escalations_no_timers(client):
    """POST /api/v1/check-escalations returns empty when no expired timers."""
    with patch("app.routers.api.get_db_connection", fake_connection([[]])):
        resp = await client.post("/api/v1/check-escalations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["checked"] == 0
    assert body["escalated"] == 0


@pytest.mark.asyncio
async def test_check_escalations_with_expired_timer(client):
    """POST /api/v1/check-escalations escalates expired timers."""
    fake_timers = [
        {
            "id": str(uuid.uuid4()),
            "incident_id": "inc-expired-1",
            "team": "platform",
            "current_level": 1,
            "assigned_to": "omarafidi2005@gmail.com",
        }
    ]

    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    fake_policy = {"wait_minutes": 5, "notify_target": "secondary"}

    # DB calls: 1) get expired timers, 2) get schedule, 3) get policy,
    # 4) insert escalation + deactivate timer, 5) lookup policy for new timer, 6) insert timer
    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_timers, fake_schedule, fake_policy, None, None, None]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/check-escalations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["checked"] == 1
    assert body["escalated"] == 1
    assert body["details"][0]["action"] == "escalated"


# ── GET /api/v1/metrics/oncall -- on-call metrics ────────────


@pytest.mark.asyncio
async def test_get_oncall_metrics(client):
    """GET /api/v1/metrics/oncall returns on-call metrics."""
    fake_esc_count = {"cnt": 5}
    fake_esc_by_team = [{"team": "platform", "cnt": 3}]
    fake_incident_summary = {"total": 50, "avg_mtta": 180.0, "avg_mttr": 900.0}
    fake_load = [{"assigned_to": "Omar Afidi", "cnt": 3}]

    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_esc_count, fake_esc_by_team, fake_incident_summary, fake_load]),
    ):
        resp = await client.get("/api/v1/metrics/oncall")

    assert resp.status_code == 200
    body = resp.json()
    assert "total_escalations" in body
    assert "escalation_rate_pct" in body
    assert "avg_mtta_seconds" in body


# ── POST /api/v1/escalate with level 2 ───────────────────────


@pytest.mark.asyncio
async def test_escalate_level_2_to_manager(client):
    """POST /api/v1/escalate with level=2 escalates to manager."""
    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_schedule, None, None, None, None]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post(
                "/api/v1/escalate",
                json={
                    "incident_id": "inc-l2",
                    "team": "platform",
                    "level": 2,
                    "reason": "Secondary did not respond",
                },
            )

    assert resp.status_code == 201
    body = resp.json()
    assert body["level"] == 2
    assert body["to_engineer"] == "admin@expertmind.local"


# ── GET /metrics ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_metrics_contains_custom_metrics(client):
    """Metrics endpoint exposes escalations_total and oncall_current."""
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    text = resp.text
    assert "escalations_total" in text


# ══════════════════════════════════════════════════════════════
# String-engineers branches (json.loads path)
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_schedule_string_engineers(client, sample_schedule_payload):
    """POST /api/v1/schedules handles engineers returned as a JSON string."""
    fake_row = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": json.dumps(
            [
                {
                    "name": "Omar Afidi",
                    "email": "omarafidi2005@gmail.com",
                    "primary": True,
                },
            ]
        ),
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    with patch("app.routers.api.get_db_connection", fake_connection([fake_row])):
        resp = await client.post("/api/v1/schedules", json=sample_schedule_payload)

    assert resp.status_code == 201
    assert len(resp.json()["engineers"]) == 1


@pytest.mark.asyncio
async def test_list_schedules_string_engineers(client):
    """GET /api/v1/schedules handles engineers stored as JSON string."""
    fake_rows = [
        {
            "id": str(uuid.uuid4()),
            "team": "platform",
            "rotation_type": "weekly",
            "start_date": date(2026, 1, 1),
            "engineers": json.dumps([{"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True}]),
            "escalation_minutes": 5,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
    ]

    with patch("app.routers.api.get_db_connection", fake_connection([fake_rows])):
        resp = await client.get("/api/v1/schedules")

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_get_current_oncall_string_engineers(client):
    """GET /api/v1/oncall/current handles engineers stored as JSON string."""
    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": json.dumps(
            [
                {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
                {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
            ]
        ),
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    with patch("app.routers.api.get_db_connection", fake_connection([fake_schedule])):
        resp = await client.get("/api/v1/oncall/current?team=platform")

    assert resp.status_code == 200
    assert resp.json()["primary"]["role"] == "primary"


# ══════════════════════════════════════════════════════════════
# DB-error paths
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_schedules_db_error(client):
    """GET /api/v1/schedules returns 500 on DB error."""
    with patch("app.routers.api.get_db_connection", side_effect=Exception("DB down")):
        resp = await client.get("/api/v1/schedules")
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_get_current_oncall_db_error(client):
    """GET /api/v1/oncall/current returns 500 on DB error."""
    with patch("app.routers.api.get_db_connection", side_effect=Exception("DB down")):
        resp = await client.get("/api/v1/oncall/current?team=platform")
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_get_current_oncall_empty_engineers(client):
    """GET /api/v1/oncall/current returns 404 when schedule has no engineers."""
    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    with patch("app.routers.api.get_db_connection", fake_connection([fake_schedule])):
        resp = await client.get("/api/v1/oncall/current?team=platform")
    assert resp.status_code == 404
    assert "No engineers" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_escalate_db_error_schedule_lookup(client, sample_escalate_payload):
    """POST /api/v1/escalate returns 500 when schedule lookup fails."""
    with patch("app.routers.api.get_db_connection", side_effect=Exception("DB down")):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/escalate", json=sample_escalate_payload)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_escalate_empty_engineers(client, sample_escalate_payload):
    """POST /api/v1/escalate returns 404 when schedule has no engineers."""
    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    with patch("app.routers.api.get_db_connection", fake_connection([fake_schedule])):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/escalate", json=sample_escalate_payload)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_escalate_no_team_defaults_to_platform(client):
    """POST /api/v1/escalate defaults team to 'platform' when missing."""
    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_schedule, None, None, None, None]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post(
                "/api/v1/escalate",
                json={"incident_id": "inc-no-team", "team": None},
            )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_escalate_db_error_recording(client, sample_escalate_payload):
    """POST /api/v1/escalate returns 500 when recording the escalation fails."""
    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    # 1) schedule lookup OK, 2) insert escalation FAIL
    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_schedule, Exception("DB down")]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/escalate", json=sample_escalate_payload)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_escalate_deactivate_timer_error(client, sample_escalate_payload):
    """POST /api/v1/escalate succeeds even when deactivating timers fails (non-critical)."""
    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    # 1) schedule OK, 2) insert escalation OK, 3) deactivate timer FAIL, 4) timer policy OK, 5) timer insert OK
    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_schedule, None, Exception("DB down"), None, None]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/escalate", json=sample_escalate_payload)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_escalate_timer_errors(client, sample_escalate_payload):
    """POST /api/v1/escalate succeeds even when timer creation fails."""
    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    # 1) schedule OK, 2) insert esc OK, 3) deactivate OK, 4) timer policy FAIL, 5) timer insert FAIL
    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_schedule, None, None, Exception("DB"), Exception("DB")]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/escalate", json=sample_escalate_payload)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_escalate_notification_failure(client, sample_escalate_payload):
    """POST /api/v1/escalate succeeds even when notification service is down."""
    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_schedule, None, None, None, None]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClientDown):
            resp = await client.post("/api/v1/escalate", json=sample_escalate_payload)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_escalate_notification_bad_response(client, sample_escalate_payload):
    """POST /api/v1/escalate handles notification service returning 4xx."""
    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    BadClient = make_fake_async_client(post_status=500)
    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_schedule, None, None, None, None]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", BadClient):
            resp = await client.post("/api/v1/escalate", json=sample_escalate_payload)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_list_escalations_db_error(client):
    """GET /api/v1/escalations returns 500 on DB error."""
    with patch("app.routers.api.get_db_connection", side_effect=Exception("DB down")):
        resp = await client.get("/api/v1/escalations")
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_list_escalations_with_incident_filter(client):
    """GET /api/v1/escalations?incident_id=... filters properly."""
    fake_rows = [
        {
            "id": str(uuid.uuid4()),
            "incident_id": "inc-filter",
            "from_engineer": "omarafidi2005@gmail.com",
            "to_engineer": "omarafidi2005@gmail.com",
            "level": 1,
            "reason": "Timeout",
            "escalated_at": datetime(2026, 2, 10, 12, 0, 0, tzinfo=timezone.utc),
        }
    ]

    with patch("app.routers.api.get_db_connection", fake_connection([fake_rows])):
        resp = await client.get("/api/v1/escalations?incident_id=inc-filter")

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


# ── Escalation policy error paths ────────────────────────────


@pytest.mark.asyncio
async def test_create_policy_db_error(client, sample_policy_payload):
    """POST /api/v1/escalation-policies returns 500 on DB error."""
    with patch("app.routers.api.get_db_connection", side_effect=Exception("DB down")):
        resp = await client.post("/api/v1/escalation-policies", json=sample_policy_payload)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_list_policies_db_error(client):
    """GET /api/v1/escalation-policies returns 500 on DB error."""
    with patch("app.routers.api.get_db_connection", side_effect=Exception("DB down")):
        resp = await client.get("/api/v1/escalation-policies")
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_list_policies_with_team_filter(client):
    """GET /api/v1/escalation-policies?team=backend filters by team."""
    fake_rows = [
        {
            "team": "backend",
            "level": 1,
            "wait_minutes": 10,
            "notify_target": "secondary",
        },
    ]

    with patch("app.routers.api.get_db_connection", fake_connection([fake_rows])):
        resp = await client.get("/api/v1/escalation-policies?team=backend")

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_get_policy_db_error(client):
    """GET /api/v1/escalation-policies/platform returns 500 on DB error."""
    with patch("app.routers.api.get_db_connection", side_effect=Exception("DB down")):
        resp = await client.get("/api/v1/escalation-policies/platform")
    assert resp.status_code == 500


# ══════════════════════════════════════════════════════════════
# check-escalations — exhaustive branch coverage
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_check_escalations_db_error(client):
    """POST /api/v1/check-escalations returns 500 when timer query fails."""
    with patch("app.routers.api.get_db_connection", side_effect=Exception("DB down")):
        resp = await client.post("/api/v1/check-escalations")
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_check_escalations_incident_acknowledged(client):
    """POST /api/v1/check-escalations skips acknowledged incidents."""
    fake_timers = [
        {
            "id": str(uuid.uuid4()),
            "incident_id": "inc-ack",
            "team": "platform",
            "current_level": 1,
            "assigned_to": "omarafidi2005@gmail.com",
        }
    ]

    # httpx returns acknowledged status
    AckClient = make_fake_async_client(get_json={"status": "acknowledged"})

    # 1) get timers, 2) deactivate timer (for acknowledged)
    with patch("app.routers.api.get_db_connection", fake_connection([fake_timers, None])):
        with patch("app.routers.api.httpx.AsyncClient", AckClient):
            resp = await client.post("/api/v1/check-escalations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["checked"] == 1
    assert body["escalated"] == 0
    assert body["details"][0]["action"] == "skipped"
    assert "acknowledged" in body["details"][0]["reason"]


@pytest.mark.asyncio
async def test_check_escalations_incident_ack_deactivate_error(client):
    """POST /api/v1/check-escalations handles DB error when deactivating acknowledged timer."""
    fake_timers = [
        {
            "id": str(uuid.uuid4()),
            "incident_id": "inc-ack-err",
            "team": "platform",
            "current_level": 1,
            "assigned_to": "omarafidi2005@gmail.com",
        }
    ]

    AckClient = make_fake_async_client(get_json={"status": "resolved"})

    # 1) get timers OK, 2) deactivate timer FAIL (non-critical)
    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_timers, Exception("DB")]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", AckClient):
            resp = await client.post("/api/v1/check-escalations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["details"][0]["action"] == "skipped"


@pytest.mark.asyncio
async def test_check_escalations_httpx_error(client):
    """POST /api/v1/check-escalations handles httpx failure when checking incident."""
    fake_timers = [
        {
            "id": str(uuid.uuid4()),
            "incident_id": "inc-http-err",
            "team": "platform",
            "current_level": 1,
            "assigned_to": "omarafidi2005@gmail.com",
        }
    ]

    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    fake_policy = {"wait_minutes": 5, "notify_target": "secondary"}

    # httpx GET raises
    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_timers, fake_schedule, fake_policy, None, None, None]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClientDown):
            resp = await client.post("/api/v1/check-escalations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["escalated"] == 1


@pytest.mark.asyncio
async def test_check_escalations_no_schedule(client):
    """POST /api/v1/check-escalations skips timers with no schedule."""
    fake_timers = [
        {
            "id": str(uuid.uuid4()),
            "incident_id": "inc-no-sched",
            "team": "orphaned",
            "current_level": 1,
            "assigned_to": "omarafidi2005@gmail.com",
        }
    ]

    # 1) get timers, 2) schedule lookup returns None
    with patch("app.routers.api.get_db_connection", fake_connection([fake_timers, None])):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/check-escalations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["checked"] == 1
    assert body["escalated"] == 0
    assert body["details"][0]["action"] == "skipped"
    assert "No schedule" in body["details"][0]["reason"]


@pytest.mark.asyncio
async def test_check_escalations_schedule_lookup_error(client):
    """POST /api/v1/check-escalations skips timer when schedule lookup raises."""
    fake_timers = [
        {
            "id": str(uuid.uuid4()),
            "incident_id": "inc-sched-err",
            "team": "platform",
            "current_level": 1,
            "assigned_to": "omarafidi2005@gmail.com",
        }
    ]

    # 1) get timers OK, 2) schedule lookup FAIL → schedule=None → skip
    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_timers, Exception("DB")]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/check-escalations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["details"][0]["action"] == "skipped"


@pytest.mark.asyncio
async def test_check_escalations_policy_manager_target(client):
    """POST /api/v1/check-escalations escalates to manager when policy says so."""
    fake_timers = [
        {
            "id": str(uuid.uuid4()),
            "incident_id": "inc-mgr",
            "team": "platform",
            "current_level": 2,
            "assigned_to": "omarafidi2005@gmail.com",
        }
    ]

    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    fake_policy = {"wait_minutes": 10, "notify_target": "manager"}

    # 1) timers, 2) schedule, 3) policy, 4) record escalation, 5) timer policy, 6) timer insert
    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_timers, fake_schedule, fake_policy, None, None, None]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/check-escalations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["escalated"] == 1
    assert body["details"][0]["to"] == "admin@expertmind.local"


@pytest.mark.asyncio
async def test_check_escalations_policy_direct_email(client):
    """POST /api/v1/check-escalations escalates to direct email from policy."""
    fake_timers = [
        {
            "id": str(uuid.uuid4()),
            "incident_id": "inc-direct",
            "team": "platform",
            "current_level": 1,
            "assigned_to": "omarafidi2005@gmail.com",
        }
    ]

    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    fake_policy = {"wait_minutes": 5, "notify_target": "teamlead@example.com"}

    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_timers, fake_schedule, fake_policy, None, None, None]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/check-escalations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["details"][0]["to"] == "teamlead@example.com"


@pytest.mark.asyncio
async def test_check_escalations_no_policy_level_gt1(client):
    """POST /api/v1/check-escalations defaults to manager when no policy and level > 1."""
    fake_timers = [
        {
            "id": str(uuid.uuid4()),
            "incident_id": "inc-nopol",
            "team": "platform",
            "current_level": 3,
            "assigned_to": "omarafidi2005@gmail.com",
        }
    ]

    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    # No policy found (None)
    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_timers, fake_schedule, None, None, None, None]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/check-escalations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["details"][0]["to"] == "admin@expertmind.local"


@pytest.mark.asyncio
async def test_check_escalations_no_policy_level1_secondary(client):
    """POST /api/v1/check-escalations defaults to secondary when no policy and level == 1."""
    fake_timers = [
        {
            "id": str(uuid.uuid4()),
            "incident_id": "inc-nopol-l1",
            "team": "platform",
            "current_level": 1,
            "assigned_to": "omarafidi2005@gmail.com",
        }
    ]

    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_timers, fake_schedule, None, None, None, None]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/check-escalations")

    assert resp.status_code == 200
    body = resp.json()
    # The actual secondary depends on rotation index at today's date
    assert body["details"][0]["to"] in ("omarafidi2005@gmail.com", "omarafidi2005@gmail.com")


@pytest.mark.asyncio
async def test_check_escalations_policy_lookup_error(client):
    """POST /api/v1/check-escalations handles DB error in policy lookup."""
    fake_timers = [
        {
            "id": str(uuid.uuid4()),
            "incident_id": "inc-pol-err",
            "team": "platform",
            "current_level": 1,
            "assigned_to": "omarafidi2005@gmail.com",
        }
    ]

    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    # 1) timers, 2) schedule, 3) policy FAIL → policy_row=None, 4) record, 5) timer policy, 6) timer insert
    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_timers, fake_schedule, Exception("DB"), None, None, None]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/check-escalations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["escalated"] == 1


@pytest.mark.asyncio
async def test_check_escalations_record_error(client):
    """POST /api/v1/check-escalations skips timer when recording escalation fails."""
    fake_timers = [
        {
            "id": str(uuid.uuid4()),
            "incident_id": "inc-rec-err",
            "team": "platform",
            "current_level": 1,
            "assigned_to": "omarafidi2005@gmail.com",
        }
    ]

    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    fake_policy = {"wait_minutes": 5, "notify_target": "secondary"}

    # 1) timers, 2) schedule, 3) policy, 4) record escalation FAIL → continue
    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_timers, fake_schedule, fake_policy, Exception("DB")]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/check-escalations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["checked"] == 1
    assert body["escalated"] == 0


@pytest.mark.asyncio
async def test_check_escalations_max_level_no_timer(client):
    """POST /api/v1/check-escalations does not start timer when max level exceeded."""
    fake_timers = [
        {
            "id": str(uuid.uuid4()),
            "incident_id": "inc-maxlvl",
            "team": "platform",
            "current_level": 99,  # Way above ESCALATION_LOOP_COUNT + 1
            "assigned_to": "admin@expertmind.local",
        }
    ]

    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    fake_policy = {"wait_minutes": 5, "notify_target": "manager"}

    # 1) timers, 2) schedule, 3) policy, 4) record escalation (no timer calls after)
    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_timers, fake_schedule, fake_policy, None]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/check-escalations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["escalated"] == 1


@pytest.mark.asyncio
async def test_check_escalations_incident_404(client):
    """POST /api/v1/check-escalations proceeds when incident service returns non-200."""
    fake_timers = [
        {
            "id": str(uuid.uuid4()),
            "incident_id": "inc-404",
            "team": "platform",
            "current_level": 1,
            "assigned_to": "omarafidi2005@gmail.com",
        }
    ]

    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    fake_policy = {"wait_minutes": 5, "notify_target": "secondary"}

    # Incident service returns 404 → incident_status stays None → escalate
    Client404 = make_fake_async_client(get_status=404, get_json={})

    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_timers, fake_schedule, fake_policy, None, None, None]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", Client404):
            resp = await client.post("/api/v1/check-escalations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["escalated"] == 1


# ══════════════════════════════════════════════════════════════
# metrics/oncall — error paths
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_oncall_metrics_escalation_db_error(client):
    """GET /api/v1/metrics/oncall handles DB error in escalation query gracefully."""
    # Both DB connections fail → all metrics are defaults
    with patch("app.routers.api.get_db_connection", side_effect=Exception("DB down")):
        resp = await client.get("/api/v1/metrics/oncall")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_escalations"] == 0
    assert body["total_incidents"] == 0


@pytest.mark.asyncio
async def test_oncall_metrics_incident_db_error(client):
    """GET /api/v1/metrics/oncall handles DB error in incident query gracefully."""
    fake_esc_count = {"cnt": 3}

    # 1) escalation count OK, 2) incident query FAIL
    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_esc_count, Exception("DB down")]),
    ):
        resp = await client.get("/api/v1/metrics/oncall")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_escalations"] == 3
    assert body["total_incidents"] == 0


@pytest.mark.asyncio
async def test_oncall_metrics_full_data(client):
    """GET /api/v1/metrics/oncall returns full metrics when all queries succeed."""
    fake_esc_count = {"cnt": 10}
    fake_esc_by_team = [{"team": "platform", "cnt": 7}]

    from contextlib import contextmanager
    from unittest.mock import MagicMock

    @contextmanager
    def _fake_conn(autocommit=False):
        conn = MagicMock()

        @contextmanager
        def _cur():
            cur = MagicMock()
            # Only one DB block now: escalation count + by-team
            cur.fetchone.return_value = fake_esc_count
            cur.fetchall.return_value = fake_esc_by_team
            yield cur

        conn.cursor = _cur
        yield conn

    # Mock the httpx.get call to incident analytics API
    fake_analytics_response = MagicMock()
    fake_analytics_response.status_code = 200
    fake_analytics_response.json.return_value = {
        "total_incidents": 100,
        "open_count": 10,
        "acknowledged_count": 5,
        "resolved_count": 85,
        "avg_mtta_seconds": 120.5,
        "avg_mttr_seconds": 600.0,
        "by_severity": {},
        "by_service": {},
    }

    with patch("app.routers.api.get_db_connection", _fake_conn):
        with patch("httpx.get", return_value=fake_analytics_response):
            resp = await client.get("/api/v1/metrics/oncall")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_escalations"] == 10
    assert body["total_incidents"] == 100
    assert body["avg_mtta_seconds"] == 120.5
    assert body["avg_mttr_seconds"] == 600.0
    assert body["escalation_rate_pct"] == 10.0
    assert body["by_team"]["platform"] == 7


@pytest.mark.asyncio
async def test_oncall_metrics_zero_incidents(client):
    """GET /api/v1/metrics/oncall handles zero total incidents (no divide-by-zero)."""
    from contextlib import contextmanager
    from unittest.mock import MagicMock

    fake_esc_count = {"cnt": 0}

    @contextmanager
    def _fake_conn(autocommit=False):
        conn = MagicMock()

        @contextmanager
        def _cur():
            cur = MagicMock()
            cur.fetchone.return_value = fake_esc_count
            cur.fetchall.return_value = []
            yield cur

        conn.cursor = _cur
        yield conn

    # Mock the httpx.get call to incident analytics API
    fake_analytics_response = MagicMock()
    fake_analytics_response.status_code = 200
    fake_analytics_response.json.return_value = {
        "total_incidents": 0,
        "open_count": 0,
        "acknowledged_count": 0,
        "resolved_count": 0,
        "avg_mtta_seconds": None,
        "avg_mttr_seconds": None,
        "by_severity": {},
        "by_service": {},
    }

    with patch("app.routers.api.get_db_connection", _fake_conn):
        with patch("httpx.get", return_value=fake_analytics_response):
            resp = await client.get("/api/v1/metrics/oncall")

    assert resp.status_code == 200
    body = resp.json()
    assert body["escalation_rate_pct"] is None
    assert body["avg_mtta_seconds"] is None


# ══════════════════════════════════════════════════════════════
# Edge-case coverage -- remaining lines
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_current_oncall_empty_engineers_json_string(client):
    """GET /api/v1/oncall/current returns 404 when engineers is JSON string '[]'."""
    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": "[]",  # valid JSON string that parses to empty list
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    with patch("app.routers.api.get_db_connection", fake_connection([fake_schedule])):
        resp = await client.get("/api/v1/oncall/current?team=platform")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_escalate_no_to_engineer(client):
    """POST /api/v1/escalate returns 422 when to_engineer resolves to empty."""
    from app.config import settings as _s

    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "solo",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    with patch("app.routers.api.get_db_connection", fake_connection([fake_schedule])):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            with patch.object(_s, "MANAGER_EMAIL", ""):
                resp = await client.post(
                    "/api/v1/escalate",
                    json={"incident_id": "inc-no-target", "team": "solo"},
                )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_escalate_timer_uses_policy_wait(client, sample_escalate_payload):
    """POST /api/v1/escalate _start_escalation_timer reads wait_minutes from policy."""
    fake_schedule = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    timer_policy = {"wait_minutes": 15}

    # 1) schedule, 2) insert esc, 3) deactivate timer, 4) timer policy FOUND, 5) timer insert
    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_schedule, None, None, timer_policy, None]),
    ):
        with patch("app.routers.api.httpx.AsyncClient", FakeAsyncClient):
            resp = await client.post("/api/v1/escalate", json=sample_escalate_payload)
    assert resp.status_code == 201


# ── POST /api/v1/schedules -- invalid timezone ──────────────────


@pytest.mark.asyncio
async def test_create_schedule_invalid_timezone(client, sample_schedule_payload):
    """POST /api/v1/schedules rejects an invalid timezone string."""
    payload = {**sample_schedule_payload, "timezone": "Invalid/TZ"}
    resp = await client.post("/api/v1/schedules", json=payload)
    assert resp.status_code == 400
    assert "Invalid timezone" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_schedule_with_handoff_and_timezone(client, sample_schedule_payload):
    """POST /api/v1/schedules with handoff_hour and timezone returns both fields."""
    payload = {**sample_schedule_payload, "handoff_hour": 8, "timezone": "US/Eastern"}
    fake_row = {
        "id": str(uuid.uuid4()),
        "team": "platform",
        "rotation_type": "weekly",
        "start_date": date(2026, 1, 1),
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ],
        "escalation_minutes": 5,
        "handoff_hour": 8,
        "timezone": "US/Eastern",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    with patch("app.routers.api.get_db_connection", fake_connection([fake_row])):
        resp = await client.post("/api/v1/schedules", json=payload)

    assert resp.status_code == 201
    body = resp.json()
    assert body["handoff_hour"] == 8
    assert body["timezone"] == "US/Eastern"


@pytest.mark.asyncio
async def test_create_schedule_reraises_http_exception(client, sample_schedule_payload):
    """Ensure HTTPException from timezone check is re-raised, not wrapped as 500."""
    payload = {**sample_schedule_payload, "timezone": "Fake/Zone"}
    resp = await client.post("/api/v1/schedules", json=payload)
    assert resp.status_code == 400


# ── POST /api/v1/timers/start ─────────────────────────────────


@pytest.mark.asyncio
async def test_start_timer_success(client):
    """POST /api/v1/timers/start creates a timer with default wait."""
    timer_payload = {
        "incident_id": "inc-timer-001",
        "team": "platform",
        "assigned_to": "omarafidi2005@gmail.com",
    }

    # Call 1: policy lookup (no policy → use default)
    # Call 2: timer INSERT
    with patch("app.routers.api.get_db_connection", fake_connection([None, None])):
        resp = await client.post("/api/v1/timers/start", json=timer_payload)

    assert resp.status_code == 201
    body = resp.json()
    assert body["incident_id"] == "inc-timer-001"
    assert body["team"] == "platform"
    assert body["assigned_to"] == "omarafidi2005@gmail.com"
    assert body["current_level"] == 1
    assert "escalate_after" in body


@pytest.mark.asyncio
async def test_start_timer_with_policy(client):
    """POST /api/v1/timers/start uses policy wait_minutes when present."""
    timer_payload = {
        "incident_id": "inc-timer-002",
        "team": "platform",
        "assigned_to": "omarafidi2005@gmail.com",
    }

    # Call 1: policy lookup found
    # Call 2: timer INSERT
    policy = {"wait_minutes": 15}
    with patch("app.routers.api.get_db_connection", fake_connection([policy, None])):
        resp = await client.post("/api/v1/timers/start", json=timer_payload)

    assert resp.status_code == 201
    body = resp.json()
    assert body["current_level"] == 1


@pytest.mark.asyncio
async def test_start_timer_policy_db_error(client):
    """POST /api/v1/timers/start handles policy lookup DB error gracefully."""
    timer_payload = {
        "incident_id": "inc-timer-003",
        "team": "platform",
        "assigned_to": "omarafidi2005@gmail.com",
    }

    # Call 1: policy lookup raises exception → falls back to default
    # Call 2: timer INSERT
    with patch("app.routers.api.get_db_connection", fake_connection([Exception("DB"), None])):
        resp = await client.post("/api/v1/timers/start", json=timer_payload)

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_start_timer_insert_db_error(client):
    """POST /api/v1/timers/start returns 500 on timer INSERT failure."""
    timer_payload = {
        "incident_id": "inc-timer-004",
        "team": "platform",
        "assigned_to": "omarafidi2005@gmail.com",
    }

    # Call 1: policy lookup ok
    # Call 2: timer INSERT fails
    with patch("app.routers.api.get_db_connection", fake_connection([None, Exception("DB")])):
        resp = await client.post("/api/v1/timers/start", json=timer_payload)

    assert resp.status_code == 500


# ── POST /api/v1/timers/cancel ────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_timer_success(client):
    """POST /api/v1/timers/cancel deactivates timer(s) and returns count."""
    cancel_payload = {"incident_id": "inc-timer-001"}

    # fetchall returns cancelled rows with team
    cancelled_rows = [{"team": "platform"}]
    with patch("app.routers.api.get_db_connection", fake_connection([cancelled_rows])):
        resp = await client.post("/api/v1/timers/cancel", json=cancel_payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["incident_id"] == "inc-timer-001"
    assert body["cancelled_count"] == 1


@pytest.mark.asyncio
async def test_cancel_timer_none_active(client):
    """POST /api/v1/timers/cancel with no active timer returns count 0."""
    cancel_payload = {"incident_id": "inc-nonexistent"}

    with patch("app.routers.api.get_db_connection", fake_connection([[]])):
        resp = await client.post("/api/v1/timers/cancel", json=cancel_payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["cancelled_count"] == 0


@pytest.mark.asyncio
async def test_cancel_timer_db_error(client):
    """POST /api/v1/timers/cancel returns 500 on DB error."""
    cancel_payload = {"incident_id": "inc-timer-001"}

    with patch("app.routers.api.get_db_connection", fake_connection([Exception("DB")])):
        resp = await client.post("/api/v1/timers/cancel", json=cancel_payload)

    assert resp.status_code == 500


# ── GET /api/v1/timers ────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_timers(client):
    """GET /api/v1/timers returns active timers."""
    fake_timers = [
        {
            "id": str(uuid.uuid4()),
            "incident_id": "inc-t-001",
            "team": "platform",
            "current_level": 1,
            "assigned_to": "omarafidi2005@gmail.com",
            "escalate_after": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            "is_active": True,
        }
    ]

    with patch("app.routers.api.get_db_connection", fake_connection([fake_timers])):
        resp = await client.get("/api/v1/timers")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["timers"][0]["incident_id"] == "inc-t-001"


@pytest.mark.asyncio
async def test_list_timers_with_team_filter(client):
    """GET /api/v1/timers?team=platform filters by team."""
    with patch("app.routers.api.get_db_connection", fake_connection([[]])):
        resp = await client.get("/api/v1/timers?team=platform")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_list_timers_with_incident_filter(client):
    """GET /api/v1/timers?incident_id=inc-x filters by incident."""
    with patch("app.routers.api.get_db_connection", fake_connection([[]])):
        resp = await client.get("/api/v1/timers?incident_id=inc-x")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_timers_with_both_filters(client):
    """GET /api/v1/timers?team=x&incident_id=y accepts both filters."""
    with patch("app.routers.api.get_db_connection", fake_connection([[]])):
        resp = await client.get("/api/v1/timers?team=platform&incident_id=inc-123")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_timers_db_error(client):
    """GET /api/v1/timers returns 500 on DB error."""
    with patch("app.routers.api.get_db_connection", fake_connection([Exception("DB")])):
        resp = await client.get("/api/v1/timers")

    assert resp.status_code == 500


# ── POST /api/v1/schedules/{id}/members ──────────────────────


@pytest.mark.asyncio
async def test_add_schedule_member_success(client):
    """POST /api/v1/schedules/{id}/members creates a member."""
    schedule_id = str(uuid.uuid4())
    member_payload = {
        "user_name": "Omar Afidi",
        "user_email": "omarafidi2005@gmail.com",
        "position": 1,
    }

    fake_schedule = {"id": schedule_id}
    fake_member_row = {
        "id": str(uuid.uuid4()),
        "schedule_id": schedule_id,
        "user_name": "Omar Afidi",
        "user_email": "omarafidi2005@gmail.com",
        "position": 1,
        "is_active": True,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    # Call 1: check schedule exists (fetchone), Call 2: INSERT member (fetchone)
    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([fake_schedule, fake_member_row]),
    ):
        resp = await client.post(f"/api/v1/schedules/{schedule_id}/members", json=member_payload)

    assert resp.status_code == 201
    body = resp.json()
    assert body["user_name"] == "Omar Afidi"
    assert body["position"] == 1
    assert body["is_active"] is True


@pytest.mark.asyncio
async def test_add_schedule_member_schedule_not_found(client):
    """POST /api/v1/schedules/{id}/members returns 404 for unknown schedule."""
    schedule_id = str(uuid.uuid4())
    member_payload = {
        "user_name": "Omar Afidi",
        "user_email": "omarafidi2005@gmail.com",
        "position": 1,
    }

    # fetchone returns None (schedule not found)
    with patch("app.routers.api.get_db_connection", fake_connection([None])):
        resp = await client.post(f"/api/v1/schedules/{schedule_id}/members", json=member_payload)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_add_schedule_member_db_error(client):
    """POST /api/v1/schedules/{id}/members returns 500 on DB error."""
    schedule_id = str(uuid.uuid4())
    member_payload = {
        "user_name": "Omar Afidi",
        "user_email": "omarafidi2005@gmail.com",
        "position": 1,
    }

    with patch("app.routers.api.get_db_connection", fake_connection([Exception("DB")])):
        resp = await client.post(f"/api/v1/schedules/{schedule_id}/members", json=member_payload)

    assert resp.status_code == 500


# ── GET /api/v1/schedules/{id}/members ───────────────────────


@pytest.mark.asyncio
async def test_list_schedule_members(client):
    """GET /api/v1/schedules/{id}/members returns members list."""
    schedule_id = str(uuid.uuid4())
    fake_rows = [
        {
            "id": str(uuid.uuid4()),
            "schedule_id": schedule_id,
            "user_name": "Omar Afidi",
            "user_email": "omarafidi2005@gmail.com",
            "position": 1,
            "is_active": True,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        },
        {
            "id": str(uuid.uuid4()),
            "schedule_id": schedule_id,
            "user_name": "Omar Afidi",
            "user_email": "omarafidi2005@gmail.com",
            "position": 2,
            "is_active": True,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        },
    ]

    with patch("app.routers.api.get_db_connection", fake_connection([fake_rows])):
        resp = await client.get(f"/api/v1/schedules/{schedule_id}/members")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["members"][0]["user_name"] == "Omar Afidi"
    assert body["members"][1]["position"] == 2


@pytest.mark.asyncio
async def test_list_schedule_members_empty(client):
    """GET /api/v1/schedules/{id}/members returns empty list."""
    schedule_id = str(uuid.uuid4())

    with patch("app.routers.api.get_db_connection", fake_connection([[]])):
        resp = await client.get(f"/api/v1/schedules/{schedule_id}/members")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["members"] == []


@pytest.mark.asyncio
async def test_list_schedule_members_db_error(client):
    """GET /api/v1/schedules/{id}/members returns 500 on DB error."""
    schedule_id = str(uuid.uuid4())

    with patch("app.routers.api.get_db_connection", fake_connection([Exception("DB")])):
        resp = await client.get(f"/api/v1/schedules/{schedule_id}/members")

    assert resp.status_code == 500


# ── DELETE /api/v1/schedules/{schedule_id} ────────────────────


@pytest.mark.asyncio
async def test_delete_schedule_success(client):
    """DELETE existing schedule → 204."""
    schedule_id = str(uuid.uuid4())

    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([{"id": schedule_id}]),
    ):
        resp = await client.delete(f"/api/v1/schedules/{schedule_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_schedule_not_found(client):
    """DELETE non-existent schedule → 404."""
    schedule_id = str(uuid.uuid4())

    with patch(
        "app.routers.api.get_db_connection",
        fake_connection([None]),
    ):
        resp = await client.delete(f"/api/v1/schedules/{schedule_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_schedule_db_error(client):
    """DELETE schedule DB error → 500."""
    schedule_id = str(uuid.uuid4())

    with patch("app.routers.api.get_db_connection", fake_connection([Exception("DB")])):
        resp = await client.delete(f"/api/v1/schedules/{schedule_id}")
    assert resp.status_code == 500


# ── Metrics: analytics API non-200 ───────────────────────────


@pytest.mark.asyncio
async def test_oncall_metrics_analytics_api_non_200(client):
    """GET /api/v1/metrics/oncall handles non-200 from incident analytics API."""
    from contextlib import contextmanager
    from unittest.mock import MagicMock as _MagicMock

    fake_esc_count = {"cnt": 2}

    @contextmanager
    def _fake_conn(autocommit=False):
        conn = _MagicMock()

        @contextmanager
        def _cur():
            cur = _MagicMock()
            cur.fetchone.return_value = fake_esc_count
            cur.fetchall.return_value = []
            yield cur

        conn.cursor = _cur
        yield conn

    fake_resp = _MagicMock()
    fake_resp.status_code = 500

    with patch("app.routers.api.get_db_connection", _fake_conn):
        with patch("httpx.get", return_value=fake_resp):
            resp = await client.get("/api/v1/metrics/oncall")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_escalations"] == 2
    assert body["total_incidents"] == 0
