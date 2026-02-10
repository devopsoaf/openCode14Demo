"""Tests for app/models.py -- Pydantic model validation."""

from datetime import date, datetime, timezone

import pytest
from app.models import (
    AutoEscalationResult,
    CurrentOnCallResponse,
    Engineer,
    EscalateRequest,
    EscalateResponse,
    EscalationPolicyCreateRequest,
    EscalationPolicyLevel,
    EscalationPolicyResponse,
    OnCallEngineer,
    OnCallMetrics,
    ScheduleCreateRequest,
    ScheduleResponse,
)
from pydantic import ValidationError


def test_engineer_model():
    """Engineer model validates correctly."""
    eng = Engineer(name="Omar Afidi", email="omarafidi2005@gmail.com", primary=True)
    assert eng.name == "Omar Afidi"
    assert eng.primary is True


def test_schedule_create_request():
    """ScheduleCreateRequest validates correctly."""
    req = ScheduleCreateRequest(
        team="platform",
        rotation_type="weekly",
        start_date="2026-01-01",
        engineers=[
            Engineer(name="Omar Afidi", email="omarafidi2005@gmail.com", primary=True),
        ],
        escalation_minutes=5,
    )
    assert req.team == "platform"
    assert len(req.engineers) == 1


def test_schedule_create_requires_engineers():
    """ScheduleCreateRequest requires at least one engineer."""
    with pytest.raises(ValidationError):
        ScheduleCreateRequest(
            team="platform",
            rotation_type="weekly",
            start_date="2026-01-01",
            engineers=[],
            escalation_minutes=5,
        )


def test_escalate_request():
    """EscalateRequest validates correctly."""
    req = EscalateRequest(incident_id="inc-123", team="platform")
    assert req.incident_id == "inc-123"
    assert req.reason is None
    assert req.level is None


def test_escalate_request_with_level():
    """EscalateRequest accepts optional level."""
    req = EscalateRequest(incident_id="inc-123", team="platform", level=2)
    assert req.level == 2


def test_schedule_response():
    """ScheduleResponse serializes correctly."""
    resp = ScheduleResponse(
        id="sched-1",
        team="platform",
        rotation_type="weekly",
        start_date=date(2026, 1, 1),
        engineers=[Engineer(name="Omar Afidi", email="omarafidi2005@gmail.com", primary=True)],
        escalation_minutes=5,
        created_at=datetime(2026, 1, 1),
    )
    assert resp.team == "platform"


def test_current_oncall_response():
    """CurrentOnCallResponse serializes correctly."""
    resp = CurrentOnCallResponse(
        team="platform",
        primary=OnCallEngineer(name="Omar Afidi", email="omarafidi2005@gmail.com", role="primary"),
        secondary=OnCallEngineer(name="Omar Afidi", email="omarafidi2005@gmail.com", role="secondary"),
        schedule_id="sched-1",
        rotation_type="weekly",
        escalation_minutes=5,
    )
    assert resp.primary.name == "Omar Afidi"
    assert resp.secondary.name == "Omar Afidi"


def test_current_oncall_response_no_secondary():
    """CurrentOnCallResponse works without secondary."""
    resp = CurrentOnCallResponse(
        team="solo",
        primary=OnCallEngineer(name="Omar Afidi", email="omarafidi2005@gmail.com", role="primary"),
        schedule_id="sched-1",
        rotation_type="daily",
        escalation_minutes=10,
    )
    assert resp.secondary is None


def test_escalate_response_with_level():
    """EscalateResponse includes level."""
    resp = EscalateResponse(
        escalation_id="esc-1",
        incident_id="inc-1",
        from_engineer="omarafidi2005@gmail.com",
        to_engineer="omarafidi2005@gmail.com",
        level=2,
        reason="Timeout",
        escalated_at=datetime(2026, 2, 10, tzinfo=timezone.utc),
    )
    assert resp.level == 2
    assert resp.from_engineer == "omarafidi2005@gmail.com"


def test_escalation_policy_create_request():
    """EscalationPolicyCreateRequest validates correctly."""
    req = EscalationPolicyCreateRequest(
        team="platform",
        levels=[
            EscalationPolicyLevel(level=1, wait_minutes=5, notify_target="secondary"),
            EscalationPolicyLevel(level=2, wait_minutes=10, notify_target="manager"),
        ],
    )
    assert req.team == "platform"
    assert len(req.levels) == 2
    assert req.levels[0].wait_minutes == 5


def test_escalation_policy_create_requires_levels():
    """EscalationPolicyCreateRequest requires at least one level."""
    with pytest.raises(ValidationError):
        EscalationPolicyCreateRequest(
            team="platform",
            levels=[],
        )


def test_escalation_policy_response():
    """EscalationPolicyResponse serializes correctly."""
    resp = EscalationPolicyResponse(
        team="platform",
        levels=[EscalationPolicyLevel(level=1, wait_minutes=5, notify_target="secondary")],
    )
    assert resp.team == "platform"
    assert resp.levels[0].notify_target == "secondary"


def test_auto_escalation_result():
    """AutoEscalationResult model validates correctly."""
    result = AutoEscalationResult(
        checked=5,
        escalated=2,
        details=[{"incident_id": "inc-1", "action": "escalated"}],
    )
    assert result.checked == 5
    assert result.escalated == 2


def test_oncall_metrics():
    """OnCallMetrics model validates correctly."""
    metrics = OnCallMetrics(
        total_incidents=100,
        total_escalations=12,
        escalation_rate_pct=12.0,
        avg_mtta_seconds=180.5,
        avg_mttr_seconds=900.0,
        oncall_load={"Omar Afidi": 5},
        by_team={"platform": 8, "backend": 4},
    )
    assert metrics.escalation_rate_pct == 12.0
    assert metrics.oncall_load["Omar Afidi"] == 5
