"""Tests for the incidents API — POST, GET, list, PATCH, metrics, analytics.

All database calls are mocked so these run without PostgreSQL.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from helpers import fake_connection as _fake_connection


# Simulate external services being down
class _FakeAsyncClientDown:
    def __init__(self, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def get(self, *a, **kw):
        raise Exception("connection refused")

    async def post(self, *a, **kw):
        raise Exception("connection refused")


class _FakeResponse:
    """Minimal response object for mocked httpx."""

    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


class _FakeAsyncClientUp:
    """External services respond successfully."""

    def __init__(self, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def get(self, url, **kw):
        if "oncall" in url:
            return _FakeResponse(
                200,
                {
                    "primary": {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com"},
                    "secondary": {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com"},
                },
            )
        return _FakeResponse(200, {})

    async def post(self, url, **kw):
        return _FakeResponse(200, {"status": "ok"})


class _FakeAsyncClientOncallUpNotifDown:
    """Oncall service up but notification service fails."""

    def __init__(self, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def get(self, url, **kw):
        if "oncall" in url:
            return _FakeResponse(
                200,
                {"primary": {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com"}},
            )
        return _FakeResponse(200, {})

    async def post(self, url, **kw):
        if "notify" in url:
            raise Exception("notification down")
        return _FakeResponse(200, {"status": "ok"})


class _FakeAsyncClientTimerDown:
    """Oncall GET succeeds, timer POST fails, notifications work."""

    def __init__(self, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def get(self, url, **kw):
        if "oncall" in url:
            return _FakeResponse(
                200,
                {"primary": {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com"}},
            )
        return _FakeResponse(200, {})

    async def post(self, url, **kw):
        if "timers" in url:
            raise Exception("timer service down")
        return _FakeResponse(200, {"status": "ok"})


class _FakeAsyncClientCancelDown:
    """Timer cancel POST fails, notifications work."""

    def __init__(self, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def get(self, *a, **kw):
        return _FakeResponse(200, {})

    async def post(self, url, **kw):
        if "timers/cancel" in url:
            raise Exception("timer cancel failed")
        return _FakeResponse(200, {"status": "ok"})


def _make_incident_row(
    incident_id="inc-test123",
    severity="low",
    status="open",
    assigned_to=None,
    notes="[]",
    acknowledged_at=None,
    resolved_at=None,
):
    """Build a dict mimicking a DB row from incidents.incidents."""
    now = datetime.now(timezone.utc)
    return {
        "id": uuid.uuid4(),
        "incident_id": incident_id,
        "title": "[LOW] test-svc: Unit test",
        "description": "test",
        "service": "test-svc",
        "severity": severity,
        "status": status,
        "assigned_to": assigned_to,
        "notes": notes,
        "created_at": now - timedelta(minutes=10),
        "acknowledged_at": acknowledged_at,
        "resolved_at": resolved_at,
        "updated_at": now,
    }


# ── POST /api/v1/incidents ───────────────────────────────────


@pytest.mark.asyncio
async def test_create_incident(client, sample_incident_payload):
    """Creating an incident stores it and returns 201."""
    row = _make_incident_row()

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(autocommit=True),  # INSERT
        ],
    ):
        with patch("httpx.AsyncClient", _FakeAsyncClientDown):
            resp = await client.post("/api/v1/incidents", json=sample_incident_payload)

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "open"
    assert body["service"] == "test-svc"


@pytest.mark.asyncio
async def test_create_incident_validation_error(client):
    """Missing required fields returns 422."""
    resp = await client.post("/api/v1/incidents", json={"title": "X"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_incident_bad_severity(client):
    resp = await client.post(
        "/api/v1/incidents",
        json={"title": "X", "service": "x", "severity": "INVALID"},
    )
    assert resp.status_code == 422


# ── GET /api/v1/incidents (list) ─────────────────────────────


def _list_connection(total: int, rows: list):
    """Return a get_db_connection CM whose cursor serves COUNT then SELECT."""

    @contextmanager
    def _ctx(autocommit=False):
        fetch_one_results = iter([{"cnt": total}])
        fetch_all_results = iter([rows])

        cur = MagicMock()
        cur.fetchone = MagicMock(side_effect=lambda: next(fetch_one_results))
        cur.fetchall = MagicMock(side_effect=lambda: next(fetch_all_results))

        conn = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        yield conn

    return _ctx


@pytest.mark.asyncio
async def test_list_incidents(client):
    rows = [_make_incident_row(assigned_to="omarafidi2005@gmail.com")]

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _list_connection(total=1, rows=rows)(),
        ],
    ):
        resp = await client.get("/api/v1/incidents")

    assert resp.status_code == 200
    body = resp.json()
    assert "incidents" in body
    assert body["total"] == 1
    assert "limit" in body
    assert "offset" in body


@pytest.mark.asyncio
async def test_list_incidents_with_filters(client):
    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _list_connection(total=0, rows=[])(),
        ],
    ):
        resp = await client.get("/api/v1/incidents?status=open&severity=high&service=web")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ── GET /api/v1/incidents/{incident_id} ──────────────────────


@pytest.mark.asyncio
async def test_get_incident_found(client):
    row = _make_incident_row(incident_id="inc-found")

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(),  # incident row
            _fake_connection([[]])(),  # linked alerts (empty)
        ],
    ):
        resp = await client.get("/api/v1/incidents/inc-found")

    assert resp.status_code == 200
    body = resp.json()
    assert body["incident_id"] == "inc-found"
    assert "alerts" in body


@pytest.mark.asyncio
async def test_get_incident_not_found(client):
    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([None])(),
        ],
    ):
        resp = await client.get("/api/v1/incidents/inc-nope")
    assert resp.status_code == 404


# ── PATCH /api/v1/incidents/{incident_id} — acknowledge ──────


@pytest.mark.asyncio
async def test_patch_acknowledge(client):
    """Acknowledging sets acknowledged_at and returns updated incident."""
    now = datetime.now(timezone.utc)
    row = _make_incident_row(incident_id="inc-ack", status="open")
    updated = _make_incident_row(incident_id="inc-ack", status="acknowledged", acknowledged_at=now)

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(),  # fetch current
            _fake_connection([updated])(autocommit=True),  # UPDATE RETURNING
        ],
    ):
        resp = await client.patch(
            "/api/v1/incidents/inc-ack",
            json={"status": "acknowledged"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "acknowledged"


# ── PATCH — resolve ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_resolve(client):
    """Resolving sets resolved_at and returns updated incident."""
    now = datetime.now(timezone.utc)
    row = _make_incident_row(
        incident_id="inc-res",
        status="acknowledged",
        acknowledged_at=now - timedelta(minutes=5),
    )
    updated = _make_incident_row(
        incident_id="inc-res",
        status="resolved",
        acknowledged_at=now - timedelta(minutes=5),
        resolved_at=now,
    )

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(),
            _fake_connection([updated])(autocommit=True),
        ],
    ):
        resp = await client.patch(
            "/api/v1/incidents/inc-res",
            json={"status": "resolved"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"


# ── PATCH — add note ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_add_note(client):
    row = _make_incident_row(incident_id="inc-note")
    updated = _make_incident_row(incident_id="inc-note")
    updated["notes"] = ["[2026-02-09T00:00:00+00:00] investigating root cause"]

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(),
            _fake_connection([updated])(autocommit=True),
        ],
    ):
        resp = await client.patch(
            "/api/v1/incidents/inc-note",
            json={"note": "investigating root cause"},
        )

    assert resp.status_code == 200
    assert len(resp.json()["notes"]) >= 1


# ── PATCH — no fields → 400 ──────────────────────────────────


@pytest.mark.asyncio
async def test_patch_empty_body(client):
    row = _make_incident_row(incident_id="inc-empty")

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(),
        ],
    ):
        resp = await client.patch("/api/v1/incidents/inc-empty", json={})
    assert resp.status_code == 400


# ── PATCH — incident not found ───────────────────────────────


@pytest.mark.asyncio
async def test_patch_not_found(client):
    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([None])(),
        ],
    ):
        resp = await client.patch(
            "/api/v1/incidents/inc-nope",
            json={"status": "acknowledged"},
        )
    assert resp.status_code == 404


# ── GET /api/v1/incidents/{id}/metrics ───────────────────────


@pytest.mark.asyncio
async def test_get_incident_metrics_open(client):
    """Open incident has null MTTA/MTTR."""
    row = {
        "incident_id": "inc-met",
        "status": "open",
        "created_at": datetime.now(timezone.utc),
        "acknowledged_at": None,
        "resolved_at": None,
    }

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(),
        ],
    ):
        resp = await client.get("/api/v1/incidents/inc-met/metrics")

    assert resp.status_code == 200
    body = resp.json()
    assert body["mtta_seconds"] is None
    assert body["mttr_seconds"] is None


@pytest.mark.asyncio
async def test_get_incident_metrics_resolved(client):
    """Resolved incident has MTTA + MTTR."""
    now = datetime.now(timezone.utc)
    row = {
        "incident_id": "inc-met2",
        "status": "resolved",
        "created_at": now - timedelta(minutes=30),
        "acknowledged_at": now - timedelta(minutes=28),
        "resolved_at": now,
    }

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(),
        ],
    ):
        resp = await client.get("/api/v1/incidents/inc-met2/metrics")

    assert resp.status_code == 200
    body = resp.json()
    assert body["mtta_seconds"] == pytest.approx(120.0, abs=1.0)
    assert body["mttr_seconds"] == pytest.approx(1800.0, abs=1.0)


@pytest.mark.asyncio
async def test_get_incident_metrics_not_found(client):
    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([None])(),
        ],
    ):
        resp = await client.get("/api/v1/incidents/inc-nope/metrics")
    assert resp.status_code == 404


# ── GET /api/v1/incidents/analytics ──────────────────────────


@pytest.mark.asyncio
async def test_get_analytics(client):
    summary = {
        "total": 10,
        "open_count": 3,
        "ack_count": 2,
        "resolved_count": 5,
        "avg_mtta": 120.5,
        "avg_mttr": 3600.0,
    }
    sev_rows = [{"severity": "critical", "cnt": 4}, {"severity": "low", "cnt": 6}]
    svc_rows = [{"service": "web", "cnt": 7}, {"service": "api", "cnt": 3}]

    # Analytics uses ONE connection + ONE cursor with 3 sequential execute/fetch calls.
    fetch_one_results = iter([summary])
    fetch_all_results = iter([sev_rows, svc_rows])

    @contextmanager
    def _analytics_conn(autocommit=False):
        cur = MagicMock()
        cur.fetchone = MagicMock(side_effect=lambda: next(fetch_one_results))
        cur.fetchall = MagicMock(side_effect=lambda: next(fetch_all_results))

        conn = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        yield conn

    with patch("app.routers.api.get_db_connection", side_effect=[_analytics_conn()]):
        resp = await client.get("/api/v1/incidents/analytics")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_incidents"] == 10
    assert body["avg_mtta_seconds"] == 120.5
    assert body["by_severity"]["critical"] == 4
    assert body["by_service"]["web"] == 7


# ── POST /incidents — external services UP (oncall + timer + notif) ──


@pytest.mark.asyncio
async def test_create_incident_with_assignment(client, sample_incident_payload):
    """POST /incidents succeeds with oncall assignment + timer start + notif."""
    row = _make_incident_row()

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(autocommit=True),  # INSERT
            _fake_connection([None])(autocommit=True),  # persist assignment
        ],
    ):
        with patch("httpx.AsyncClient", _FakeAsyncClientUp):
            resp = await client.post("/api/v1/incidents", json=sample_incident_payload)

    assert resp.status_code == 201
    body = resp.json()
    assert body["assigned_to"] == "Omar Afidi"


@pytest.mark.asyncio
async def test_create_incident_oncall_non_200(client, sample_incident_payload):
    """Oncall returns non-200 → no assignment but incident still created."""
    row = _make_incident_row()

    class _OncallBad:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def get(self, *a, **kw):
            return _FakeResponse(500, {})

        async def post(self, *a, **kw):
            return _FakeResponse(200, {"status": "ok"})

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(autocommit=True),
        ],
    ):
        with patch("httpx.AsyncClient", _OncallBad):
            resp = await client.post("/api/v1/incidents", json=sample_incident_payload)

    assert resp.status_code == 201
    assert resp.json()["assigned_to"] is None


@pytest.mark.asyncio
async def test_create_incident_notification_failure(client, sample_incident_payload):
    """If notification service down, incident is still created."""
    row = _make_incident_row()

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(autocommit=True),
            _fake_connection([None])(autocommit=True),  # persist assignment
        ],
    ):
        with patch("httpx.AsyncClient", _FakeAsyncClientOncallUpNotifDown):
            resp = await client.post("/api/v1/incidents", json=sample_incident_payload)

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_create_incident_timer_start_failure(client, sample_incident_payload):
    """If timer start fails, incident is still created with assignment."""
    row = _make_incident_row()

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(autocommit=True),
            _fake_connection([None])(autocommit=True),
        ],
    ):
        with patch("httpx.AsyncClient", _FakeAsyncClientTimerDown):
            resp = await client.post("/api/v1/incidents", json=sample_incident_payload)

    assert resp.status_code == 201


# ── PATCH /incidents — timer cancellation on acknowledge/resolve ──


@pytest.mark.asyncio
async def test_patch_acknowledge_cancels_timer(client):
    """Acknowledging an incident also cancels escalation timer."""
    now = datetime.now(timezone.utc)
    row = _make_incident_row(incident_id="inc-ack-t", status="open")
    updated = _make_incident_row(
        incident_id="inc-ack-t",
        status="acknowledged",
        acknowledged_at=now,
    )

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(),
            _fake_connection([updated])(autocommit=True),
        ],
    ):
        with patch("httpx.AsyncClient", _FakeAsyncClientUp):
            resp = await client.patch(
                "/api/v1/incidents/inc-ack-t",
                json={"status": "acknowledged"},
            )

    assert resp.status_code == 200
    assert resp.json()["status"] == "acknowledged"


@pytest.mark.asyncio
async def test_patch_resolve_cancels_timer(client):
    """Resolving an incident also cancels escalation timer."""
    now = datetime.now(timezone.utc)
    row = _make_incident_row(incident_id="inc-res-t", status="open")
    updated = _make_incident_row(
        incident_id="inc-res-t",
        status="resolved",
        resolved_at=now,
    )

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(),
            _fake_connection([updated])(autocommit=True),
        ],
    ):
        with patch("httpx.AsyncClient", _FakeAsyncClientUp):
            resp = await client.patch(
                "/api/v1/incidents/inc-res-t",
                json={"status": "resolved"},
            )

    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"


@pytest.mark.asyncio
async def test_patch_acknowledge_timer_cancel_failure(client):
    """Acknowledge still succeeds even if timer cancel fails."""
    now = datetime.now(timezone.utc)
    row = _make_incident_row(incident_id="inc-ack-fail", status="open")
    updated = _make_incident_row(
        incident_id="inc-ack-fail",
        status="acknowledged",
        acknowledged_at=now,
    )

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(),
            _fake_connection([updated])(autocommit=True),
        ],
    ):
        with patch("httpx.AsyncClient", _FakeAsyncClientCancelDown):
            resp = await client.patch(
                "/api/v1/incidents/inc-ack-fail",
                json={"status": "acknowledged"},
            )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_patch_mitigated_cancels_timer(client):
    """Mitigated status also cancels escalation timer."""
    row = _make_incident_row(incident_id="inc-mit", status="open")
    updated = _make_incident_row(incident_id="inc-mit", status="mitigated")
    updated["status"] = "mitigated"

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(),
            _fake_connection([updated])(autocommit=True),
        ],
    ):
        with patch("httpx.AsyncClient", _FakeAsyncClientUp):
            resp = await client.patch(
                "/api/v1/incidents/inc-mit",
                json={"status": "mitigated"},
            )

    assert resp.status_code == 200


# ── GET /incidents/{id} — linked alerts exception ────────────


@pytest.mark.asyncio
async def test_get_incident_linked_alerts_exception(client):
    """Linked alerts query failure is handled gracefully."""
    row = _make_incident_row(incident_id="inc-alert-err")

    def _linked_alerts_error_conn(autocommit=False):
        """First conn succeeds, second raises for linked alerts."""
        raise Exception("linked alerts DB error")

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(),  # incident row
            _linked_alerts_error_conn,  # linked alerts raises
        ],
    ):
        resp = await client.get("/api/v1/incidents/inc-alert-err")

    assert resp.status_code == 200
    assert resp.json()["alerts"] == []


# ── PATCH — update returns None (not found after update) ─────


@pytest.mark.asyncio
async def test_patch_update_returns_none(client):
    """If UPDATE RETURNING yields no row, return 404."""
    row = _make_incident_row(incident_id="inc-vanish", status="open")

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(),
            _fake_connection([None])(autocommit=True),
        ],
    ):
        with patch("httpx.AsyncClient", _FakeAsyncClientUp):
            resp = await client.patch(
                "/api/v1/incidents/inc-vanish",
                json={"status": "acknowledged"},
            )

    assert resp.status_code == 404


# ── GET /incidents/analytics — avg_mtta/avg_mttr None ────────


@pytest.mark.asyncio
async def test_get_analytics_no_avg(client):
    """Analytics with no MTTA/MTTR data returns None."""
    summary = {
        "total": 0,
        "open_count": 0,
        "ack_count": 0,
        "resolved_count": 0,
        "avg_mtta": None,
        "avg_mttr": None,
    }

    fetch_one_results = iter([summary])
    fetch_all_results = iter([[], []])

    @contextmanager
    def _analytics_conn(autocommit=False):
        cur = MagicMock()
        cur.fetchone = MagicMock(side_effect=lambda: next(fetch_one_results))
        cur.fetchall = MagicMock(side_effect=lambda: next(fetch_all_results))

        conn = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        yield conn

    with patch("app.routers.api.get_db_connection", side_effect=[_analytics_conn()]):
        resp = await client.get("/api/v1/incidents/analytics")

    assert resp.status_code == 200
    assert resp.json()["avg_mtta_seconds"] is None
    assert resp.json()["avg_mttr_seconds"] is None


# ── PATCH — assign_to ────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_assign(client):
    """PATCH with assigned_to updates the assignee."""
    row = _make_incident_row(incident_id="inc-assign")
    updated = _make_incident_row(incident_id="inc-assign", assigned_to="omarafidi2005@gmail.com")

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[
            _fake_connection([row])(),
            _fake_connection([updated])(autocommit=True),
        ],
    ):
        resp = await client.patch(
            "/api/v1/incidents/inc-assign",
            json={"assigned_to": "omarafidi2005@gmail.com"},
        )

    assert resp.status_code == 200


# ── DELETE /api/v1/incidents/{incident_id} ────────────────────


@pytest.mark.asyncio
async def test_delete_incident_success(client):
    """DELETE existing incident → 204."""
    db_id = uuid.uuid4()
    find_row = {"id": db_id}

    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[_fake_connection([find_row, None, None, None])(autocommit=True)],
    ):
        resp = await client.delete("/api/v1/incidents/inc-del123")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_incident_not_found(client):
    """DELETE non-existent incident → 404."""
    with patch(
        "app.routers.api.get_db_connection",
        side_effect=[_fake_connection([None])(autocommit=True)],
    ):
        resp = await client.delete("/api/v1/incidents/inc-nope")
    assert resp.status_code == 404


# ── http_client fallback ─────────────────────────────────────


def test_http_client_fallback():
    """get_http_client() returns a fresh client when not initialised."""
    import app.http_client as hc

    original = hc._client
    try:
        hc._client = None
        c = hc.get_http_client()
        assert c is not None
    finally:
        hc._client = original


def test_http_client_returns_existing():
    """get_http_client() returns the shared client when initialised."""
    import app.http_client as hc

    sentinel = object()
    original = hc._client
    try:
        hc._client = sentinel
        assert hc.get_http_client() is sentinel
    finally:
        hc._client = original
