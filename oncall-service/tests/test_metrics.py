"""Tests for app/metrics.py -- custom Prometheus metrics."""


def test_escalations_total_counter():
    """escalations_total counter increments per team."""
    from app.metrics import escalations_total

    before = escalations_total.labels(team="platform")._value.get()
    escalations_total.labels(team="platform").inc()
    after = escalations_total.labels(team="platform")._value.get()
    assert after == before + 1


def test_oncall_current_gauge():
    """oncall_current gauge can be set."""
    from app.metrics import oncall_current

    oncall_current.labels(team="backend", engineer="omarafidi2005@gmail.com", role="primary").set(1)
    val = oncall_current.labels(team="backend", engineer="omarafidi2005@gmail.com", role="primary")._value.get()
    assert val == 1.0


def test_setup_custom_metrics():
    """setup_custom_metrics runs without error."""
    from app.metrics import setup_custom_metrics

    setup_custom_metrics()  # should not raise


def test_escalation_notifications_total():
    """escalation_notifications_total counter increments."""
    from app.metrics import escalation_notifications_total

    before = escalation_notifications_total.labels(team="platform", channel="mock", status="sent")._value.get()
    escalation_notifications_total.labels(team="platform", channel="mock", status="sent").inc()
    after = escalation_notifications_total.labels(team="platform", channel="mock", status="sent")._value.get()
    assert after == before + 1


def test_auto_escalation_runs_total():
    """auto_escalation_runs_total counter increments."""
    from app.metrics import auto_escalation_runs_total

    before = auto_escalation_runs_total._value.get()
    auto_escalation_runs_total.inc()
    after = auto_escalation_runs_total._value.get()
    assert after == before + 1


def test_active_escalation_timers_gauge():
    """active_escalation_timers gauge can be set."""
    from app.metrics import active_escalation_timers

    active_escalation_timers.labels(team="platform").set(3)
    val = active_escalation_timers.labels(team="platform")._value.get()
    assert val == 3.0


def test_escalation_rate_gauge():
    """escalation_rate gauge can be set."""
    from app.metrics import escalation_rate

    escalation_rate.set(15.5)
    val = escalation_rate._value.get()
    assert val == 15.5


def test_escalation_response_seconds_histogram():
    """escalation_response_seconds histogram can observe values."""
    from app.metrics import escalation_response_seconds

    escalation_response_seconds.labels(team="platform").observe(120)
    # No assert needed — just verifying no exception
