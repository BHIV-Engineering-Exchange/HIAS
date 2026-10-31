import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import User
from app.engine import evaluate
from app.schemas import Decision, Reason


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    session.add(User(user_id="S001", name="Test Resident", role="Resident"))
    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_unknown_user_allowed_during_emergency_mode(db):
    decision, reason, name = evaluate(
        db, "UNKNOWN_USER", {"emergency_mode": True}
    )

    assert decision == Decision.ALLOW
    assert reason == Reason.VALID
    assert name == "[EMERGENCY] Unknown User"


def test_known_user_allowed_during_emergency_mode(db):
    decision, reason, name = evaluate(
        db, "S001", {"emergency_mode": True}
    )

    assert decision == Decision.ALLOW
    assert reason == Reason.VALID
    assert "[EMERGENCY]" in name


def test_known_user_allowed_when_inside_access_window(db, monkeypatch):
    monkeypatch.setattr("app.engine.is_within_time_window", lambda *args: True)

    decision, reason, name = evaluate(
        db,
        "S001",
        {
            "emergency_mode": False,
            "access_window_start": "07:00",
            "access_window_end": "21:00",
        },
    )

    assert decision == Decision.ALLOW
    assert reason == Reason.VALID


def test_known_user_denied_outside_access_window(db, monkeypatch):
    monkeypatch.setattr("app.engine.is_within_time_window", lambda *args: False)

    decision, reason, name = evaluate(
        db,
        "S001",
        {
            "emergency_mode": False,
            "access_window_start": "07:00",
            "access_window_end": "21:00",
        },
    )

    assert decision == Decision.DENY
    assert reason == Reason.TIME_BLOCK


def test_unknown_user_denied_when_emergency_mode_disabled(db):
    decision, reason, name = evaluate(
        db, "UNKNOWN_USER", {"emergency_mode": False}
    )

    assert decision == Decision.DENY
    assert reason == Reason.UNKNOWN
