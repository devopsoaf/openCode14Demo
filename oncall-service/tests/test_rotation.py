"""Unit tests for the rotation algorithm (_compute_current_oncall)."""

from datetime import date, datetime, timezone
from unittest.mock import patch

from app.routers.api import _compute_current_oncall

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _schedule(
    rotation_type="weekly",
    start_date=date(2026, 1, 1),
    engineers=None,
    handoff_hour=9,
    tz="UTC",
):
    if engineers is None:
        engineers = [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
        ]
    return {
        "rotation_type": rotation_type,
        "start_date": start_date,
        "engineers": engineers,
        "handoff_hour": handoff_hour,
        "timezone": tz,
    }


def _utc_dt(target_date, hour=12):
    """Return a UTC datetime at the given date and hour (after handoff by default)."""
    return datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour,
        0,
        0,
        tzinfo=timezone.utc,
    )


# We mock datetime.now inside _compute_current_oncall.
# Using a side_effect that returns our fake "now" while keeping the real
# datetime class available for isinstance() checks.
_real_datetime = datetime


def _patch_now(fake_now):
    """Return a patch context that makes ``datetime.now(tz)`` return *fake_now*."""

    class _FakeDatetime(_real_datetime):
        @classmethod
        def now(cls, tz=None):
            return fake_now

    return patch("app.routers.api.datetime", _FakeDatetime)


# ---------------------------------------------------------------------------
# Weekly rotation
# ---------------------------------------------------------------------------


class TestWeeklyRotation:
    """Tests for weekly rotation logic."""

    def test_week_0_returns_first_engineer(self):
        with _patch_now(_utc_dt(date(2026, 1, 1))):
            primary, secondary = _compute_current_oncall(_schedule())
        assert primary.email == "omarafidi2005@gmail.com"
        assert secondary.email == "omarafidi2005@gmail.com"

    def test_week_1_rotates_to_second(self):
        with _patch_now(_utc_dt(date(2026, 1, 8))):
            primary, secondary = _compute_current_oncall(_schedule())
        assert primary.email == "omarafidi2005@gmail.com"
        assert secondary.email == "omarafidi2005@gmail.com"

    def test_week_wraps_around(self):
        with _patch_now(_utc_dt(date(2026, 1, 22))):
            primary, secondary = _compute_current_oncall(_schedule())
        assert primary.email == "omarafidi2005@gmail.com"
        assert secondary.email == "omarafidi2005@gmail.com"


# ---------------------------------------------------------------------------
# Daily rotation
# ---------------------------------------------------------------------------


class TestDailyRotation:
    """Tests for daily rotation logic."""

    def test_day_0_returns_first(self):
        with _patch_now(_utc_dt(date(2026, 1, 1))):
            primary, secondary = _compute_current_oncall(_schedule(rotation_type="daily"))
        assert primary.email == "omarafidi2005@gmail.com"

    def test_day_1_rotates(self):
        with _patch_now(_utc_dt(date(2026, 1, 2))):
            primary, secondary = _compute_current_oncall(_schedule(rotation_type="daily"))
        assert primary.email == "omarafidi2005@gmail.com"
        assert secondary.email == "omarafidi2005@gmail.com"

    def test_daily_wraps_around(self):
        with _patch_now(_utc_dt(date(2026, 1, 4))):
            primary, secondary = _compute_current_oncall(_schedule(rotation_type="daily"))
        assert primary.email == "omarafidi2005@gmail.com"


# ---------------------------------------------------------------------------
# Handoff-hour awareness
# ---------------------------------------------------------------------------


class TestHandoffHour:
    """Tests that rotation considers handoff_hour and timezone."""

    def test_before_handoff_uses_previous_day(self):
        """At 3 AM (handoff=9), still previous day's engineer."""
        with _patch_now(_utc_dt(date(2026, 1, 2), hour=3)):
            primary, _ = _compute_current_oncall(_schedule(rotation_type="daily"))
        # Day 2 at 3 AM → effective day 1 → delta 0 → idx 0 = Alice
        assert primary.email == "omarafidi2005@gmail.com"

    def test_after_handoff_uses_current_day(self):
        """At 10 AM (handoff=9), the new rotation has taken effect."""
        with _patch_now(_utc_dt(date(2026, 1, 2), hour=10)):
            primary, _ = _compute_current_oncall(_schedule(rotation_type="daily"))
        # Day 2 at 10 AM → effective day 2 → delta 1 → idx 1 = Bob
        assert primary.email == "omarafidi2005@gmail.com"

    def test_at_handoff_hour_uses_current_day(self):
        """At exactly handoff hour, the new rotation applies."""
        with _patch_now(_utc_dt(date(2026, 1, 2), hour=9)):
            primary, _ = _compute_current_oncall(_schedule(rotation_type="daily"))
        assert primary.email == "omarafidi2005@gmail.com"

    def test_custom_handoff_hour(self):
        """Handoff at midnight: hour 0 >= handoff_hour 0 so current day applies."""
        with _patch_now(_utc_dt(date(2026, 1, 2), hour=0)):
            primary, _ = _compute_current_oncall(_schedule(rotation_type="daily", handoff_hour=0))
        # hour 0 >= handoff_hour 0, so current day → delta 1 → idx 1 = Bob
        assert primary.email == "omarafidi2005@gmail.com"

    def test_invalid_timezone_falls_back_to_utc(self):
        """An invalid timezone string gracefully falls back to UTC."""
        with _patch_now(_utc_dt(date(2026, 1, 1), hour=12)):
            primary, _ = _compute_current_oncall(_schedule(tz="Invalid/TZ"))
        assert primary.email == "omarafidi2005@gmail.com"

    def test_missing_timezone_defaults_utc(self):
        """Schedule without timezone key defaults to UTC."""
        with _patch_now(_utc_dt(date(2026, 1, 1), hour=12)):
            schedule = {
                "rotation_type": "weekly",
                "start_date": date(2026, 1, 1),
                "engineers": [
                    {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
                    {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
                ],
            }
            primary, _ = _compute_current_oncall(schedule)
        assert primary.email == "omarafidi2005@gmail.com"

    def test_missing_handoff_hour_defaults_to_9(self):
        """Schedule without handoff_hour key defaults to 9."""
        with _patch_now(_utc_dt(date(2026, 1, 2), hour=3)):
            schedule = {
                "rotation_type": "daily",
                "start_date": date(2026, 1, 1),
                "engineers": [
                    {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
                    {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
                ],
                "timezone": "UTC",
            }
            # hour 3 < default 9 → still day 1 → delta 0 → idx 0 = Alice
            primary, _ = _compute_current_oncall(schedule)
        assert primary.email == "omarafidi2005@gmail.com"

    def test_none_timezone_defaults_utc(self):
        """Schedule with timezone=None defaults to UTC."""
        with _patch_now(_utc_dt(date(2026, 1, 1), hour=12)):
            primary, _ = _compute_current_oncall(_schedule(tz=None))
        assert primary.email == "omarafidi2005@gmail.com"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for rotation logic."""

    def test_empty_engineers_returns_none(self):
        primary, secondary = _compute_current_oncall(_schedule(engineers=[]))
        assert primary is None
        assert secondary is None

    def test_single_engineer_no_secondary(self):
        with _patch_now(_utc_dt(date(2026, 1, 1))):
            engineers = [{"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True}]
            primary, secondary = _compute_current_oncall(_schedule(engineers=engineers))
        assert primary.email == "omarafidi2005@gmail.com"
        assert secondary is None

    def test_start_date_in_future_uses_idx_zero(self):
        with _patch_now(_utc_dt(date(2025, 6, 1))):
            primary, _ = _compute_current_oncall(_schedule(start_date=date(2026, 1, 1)))
        assert primary.email == "omarafidi2005@gmail.com"

    def test_start_date_as_string(self):
        with _patch_now(_utc_dt(date(2026, 1, 1))):
            primary, _ = _compute_current_oncall(_schedule(start_date="2026-01-01"))
        assert primary.email == "omarafidi2005@gmail.com"

    def test_start_date_as_datetime(self):
        with _patch_now(_utc_dt(date(2026, 1, 1))):
            primary, _ = _compute_current_oncall(_schedule(start_date=datetime(2026, 1, 1, tzinfo=timezone.utc)))
        assert primary.email == "omarafidi2005@gmail.com"

    def test_engineers_as_json_string(self):
        import json

        with _patch_now(_utc_dt(date(2026, 1, 1))):
            engineers = json.dumps(
                [
                    {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
                    {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": False},
                ]
            )
            primary, secondary = _compute_current_oncall(_schedule(engineers=engineers))
        assert primary.email == "omarafidi2005@gmail.com"
        assert secondary.email == "omarafidi2005@gmail.com"
