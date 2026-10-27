"""
Unit tests for evaluation_engine/rule_engine.py
Tests:
  - is_within_time_window across standard and midnight-crossing windows
  - RuleEngine evaluation logic (known, unknown, time-blocked, emergency bypass)
  - Quality Gate: Deterministic execution (50 consecutive runs produce identical SHA-256 state hashes)
"""
import pytest
from evaluation_engine.rule_engine import (
    RuleEngine,
    Decision,
    Reason,
    is_within_time_window,
    compute_state_hash,
)


class TestIsWithinTimeWindow:
    def test_inside_normal_daytime_window(self):
        assert is_within_time_window("07:00", "21:00", current_time_str="12:00") is True

    def test_start_boundary(self):
        assert is_within_time_window("07:00", "21:00", current_time_str="07:00") is True

    def test_end_boundary(self):
        assert is_within_time_window("07:00", "21:00", current_time_str="21:00") is True

    def test_before_window(self):
        assert is_within_time_window("07:00", "21:00", current_time_str="06:59") is False

    def test_after_window(self):
        assert is_within_time_window("07:00", "21:00", current_time_str="21:01") is False

    def test_midnight_crossing_late_night(self):
        """23:00 is inside overnight window 22:00-06:00."""
        assert is_within_time_window("22:00", "06:00", current_time_str="23:00") is True

    def test_midnight_crossing_early_morning(self):
        """04:00 is inside overnight window 22:00-06:00."""
        assert is_within_time_window("22:00", "06:00", current_time_str="04:00") is True

    def test_midnight_crossing_daytime_blocked(self):
        """14:00 is outside overnight window 22:00-06:00."""
        assert is_within_time_window("22:00", "06:00", current_time_str="14:00") is False

    def test_malformed_time_strings_safe_false(self):
        assert is_within_time_window("invalid", "21:00") is False
        assert is_within_time_window("07:00", None) is False


class TestRuleEngine:
    @pytest.fixture
    def engine(self):
        return RuleEngine()

    def test_known_user_in_window_allowed(self, engine):
        res = engine.evaluate("S001", simulated_time="12:00")
        assert res.decision == Decision.ALLOW
        assert res.reason == Reason.VALID
        assert "Soham" in res.display_name
        assert len(res.state_hash) == 64

    def test_unknown_user_denied(self, engine):
        res = engine.evaluate("UNKNOWN_ID", simulated_time="12:00")
        assert res.decision == Decision.DENY
        assert res.reason == Reason.UNKNOWN
        assert res.display_name == "Unknown User"

    def test_known_user_outside_window_denied(self, engine):
        settings = {
            "emergency_mode": False,
            "access_window_start": "09:00",
            "access_window_end": "17:00",
        }
        res = engine.evaluate("S001", settings=settings, simulated_time="22:00")
        assert res.decision == Decision.DENY
        assert res.reason == Reason.TIME_BLOCK

    def test_emergency_mode_allows_known_user(self, engine):
        settings = {"emergency_mode": True}
        res = engine.evaluate("S001", settings=settings, simulated_time="03:00")
        assert res.decision == Decision.ALLOW
        assert res.reason == Reason.VALID
        assert "[EMERGENCY]" in res.display_name

    def test_emergency_mode_allows_unknown_user_without_crash(self, engine):
        """Bug remediation: Emergency mode must never crash on unknown user."""
        settings = {"emergency_mode": True}
        res = engine.evaluate("DOES_NOT_EXIST", settings=settings, simulated_time="03:00")
        assert res.decision == Decision.ALLOW
        assert res.reason == Reason.VALID
        assert res.display_name == "[EMERGENCY] Unknown User"

    def test_default_settings_used_when_none(self, engine):
        res = engine.evaluate("S001", settings=None, simulated_time="12:00")
        assert res.decision == Decision.ALLOW

    def test_deterministic_execution_50_runs(self, engine):
        """
        Quality Gate: Deterministic execution:
        50 consecutive runs must produce identical SHA-256 state hashes.
        """
        hashes = set()
        for _ in range(50):
            res = engine.evaluate("S001", simulated_time="14:30")
            hashes.add(res.state_hash)

        assert len(hashes) == 1, f"Expected 1 unique hash across 50 runs, got {len(hashes)}"
