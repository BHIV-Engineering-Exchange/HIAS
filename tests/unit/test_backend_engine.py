"""
Unit tests for backend/app/engine.py — evaluate() and is_within_time_window().
All tests use an in-memory SQLite DB via SQLAlchemy with StaticPool.
"""
import pytest
from unittest.mock import patch
from app.engine import evaluate, is_within_time_window, seed_db
from app.schemas import Decision, Reason
from app.database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def db():
    """Provide a fresh in-memory SQLite session per test."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)
    session = TestSession()
    seed_db(session)
    yield session
    session.close()


# ---------------------------------------------------------------------------
# is_within_time_window — time-window logic tests
# ---------------------------------------------------------------------------

class TestIsWithinTimeWindow:
    def test_inside_normal_window(self):
        with patch("app.engine.time.strftime", return_value="12:00"):
            assert is_within_time_window("07:00", "21:00") is True

    def test_exactly_on_start_boundary(self):
        with patch("app.engine.time.strftime", return_value="07:00"):
            assert is_within_time_window("07:00", "21:00") is True

    def test_exactly_on_end_boundary(self):
        with patch("app.engine.time.strftime", return_value="21:00"):
            assert is_within_time_window("07:00", "21:00") is True

    def test_before_normal_window(self):
        with patch("app.engine.time.strftime", return_value="06:59"):
            assert is_within_time_window("07:00", "21:00") is False

    def test_after_normal_window(self):
        with patch("app.engine.time.strftime", return_value="21:01"):
            assert is_within_time_window("07:00", "21:00") is False

    def test_midnight_crossing_in_window(self):
        with patch("app.engine.time.strftime", return_value="22:30"):
            assert is_within_time_window("22:00", "06:00") is True

    def test_midnight_crossing_early_morning(self):
        with patch("app.engine.time.strftime", return_value="02:00"):
            assert is_within_time_window("22:00", "06:00") is True

    def test_midnight_crossing_outside_window(self):
        with patch("app.engine.time.strftime", return_value="12:00"):
            assert is_within_time_window("22:00", "06:00") is False


# ---------------------------------------------------------------------------
# evaluate — decision engine logic tests
# ---------------------------------------------------------------------------

class TestEvaluate:
    def test_known_user_in_window_is_allowed(self, db):
        with patch("app.engine.time.strftime", return_value="12:00"):
            decision, reason, name = evaluate(db, "S001")
        assert decision == Decision.ALLOW
        assert reason == Reason.VALID
        assert "Soham" in name

    def test_unknown_user_is_denied(self, db):
        decision, reason, name = evaluate(db, "XXXX")
        assert decision == Decision.DENY
        assert reason == Reason.UNKNOWN
        assert name == "Unknown User"

    def test_known_user_outside_window_is_denied(self, db):
        settings = {
            "emergency_mode": False,
            "access_window_start": "09:00",
            "access_window_end": "10:00",
        }
        with patch("app.engine.time.strftime", return_value="23:00"):
            decision, reason, name = evaluate(db, "S001", settings)
        assert decision == Decision.DENY
        assert reason == Reason.TIME_BLOCK

    def test_emergency_mode_allows_known_user(self, db):
        settings = {
            "emergency_mode": True,
            "access_window_start": "09:00",
            "access_window_end": "10:00",
        }
        with patch("app.engine.time.strftime", return_value="23:00"):
            decision, reason, name = evaluate(db, "S001", settings)
        assert decision == Decision.ALLOW
        assert "[EMERGENCY]" in name

    def test_emergency_mode_allows_unknown_user_without_crash(self, db):
        settings = {"emergency_mode": True}
        decision, reason, name = evaluate(db, "DOESNOTEXIST", settings)
        assert decision == Decision.ALLOW
        assert "[EMERGENCY]" in name
        assert name == "[EMERGENCY] Unknown User"

    def test_default_settings_used_when_none(self, db):
        with patch("app.engine.time.strftime", return_value="12:00"):
            decision, reason, name = evaluate(db, "S001", None)
        assert decision == Decision.ALLOW

    def test_deterministic_output_50_runs(self, db):
        with patch("app.engine.time.strftime", return_value="12:00"):
            results = [evaluate(db, "S001") for _ in range(50)]
        assert len(set(results)) == 1, "Output must be deterministic"
