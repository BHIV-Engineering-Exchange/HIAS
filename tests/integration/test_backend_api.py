"""
Integration tests for backend FastAPI app (app.main).
Uses FastAPI TestClient with an in-memory SQLite database via StaticPool.
Error boundaries, status codes, and response schemas are all verified.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.engine import seed_db

# ---------------------------------------------------------------------------
# Test DB Setup — in-memory SQLite with StaticPool for connection persistence
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

Base.metadata.create_all(bind=test_engine)
_seed_session = TestingSessionLocal()
seed_db(_seed_session)
_seed_session.close()


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_check_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


# ---------------------------------------------------------------------------
# Access Events
# ---------------------------------------------------------------------------

class TestAccessEvent:
    def test_valid_access_event_allow(self, client):
        resp = client.post("/access/event", json={
            "user_id": "S001", "method": "RFID", "device_id": "door_in_01"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "decision" in data
        assert "trace_id" in data

    def test_duplicate_scan_returns_429(self, client):
        payload = {"user_id": "S003", "method": "RFID", "device_id": "door_in_02"}
        client.post("/access/event", json=payload)
        resp = client.post("/access/event", json=payload)
        assert resp.status_code == 429

    def test_missing_required_field_returns_422(self, client):
        resp = client.post("/access/event", json={"user_id": "S001", "method": "RFID"})
        assert resp.status_code == 422

    def test_invalid_method_returns_422(self, client):
        resp = client.post("/access/event", json={
            "user_id": "S001", "method": "FINGERPRINT", "device_id": "door_in_01"
        })
        assert resp.status_code == 422

    def test_empty_user_id_returns_422(self, client):
        resp = client.post("/access/event", json={
            "user_id": "", "method": "RFID", "device_id": "door_01"
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Events List
# ---------------------------------------------------------------------------

class TestEventsList:
    def test_get_events_returns_200(self, client):
        resp = client.get("/events")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_events_with_limit(self, client):
        resp = client.get("/events?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()) <= 2


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class TestSettings:
    def test_get_settings_returns_200(self, client):
        resp = client.get("/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "emergency_mode" in data

    def test_post_settings_valid_update(self, client):
        resp = client.post("/settings", json={"emergency_mode": True})
        assert resp.status_code == 200
        assert resp.json()["emergency_mode"] is True
        client.post("/settings", json={"emergency_mode": False})

    def test_post_settings_extra_field_returns_422(self, client):
        resp = client.post("/settings", json={"unknown_key": "bad_value"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class TestUsers:
    def test_get_all_users_returns_200(self, client):
        resp = client.get("/users")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) > 0

    def test_enroll_user_valid(self, client):
        resp = client.post("/users", json={"user_id": "T999", "name": "Test Resident"})
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "T999"

    def test_enroll_user_missing_name_returns_422(self, client):
        resp = client.post("/users", json={"user_id": "T888"})
        assert resp.status_code == 422

    def test_enroll_user_empty_user_id_returns_422(self, client):
        resp = client.post("/users", json={"user_id": "", "name": "Someone"})
        assert resp.status_code == 422

    def test_enroll_duplicate_user_returns_400(self, client):
        client.post("/users", json={"user_id": "T777", "name": "First"})
        resp = client.post("/users", json={"user_id": "T777", "name": "Duplicate"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Stats, Reports, Alerts
# ---------------------------------------------------------------------------

class TestReportsAndAlerts:
    def test_get_stats_summary_returns_200(self, client):
        resp = client.get("/stats/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data and "granted" in data and "denied" in data

    def test_get_reports_stats_returns_200(self, client):
        resp = client.get("/reports/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "hourly_distribution" in data
        assert len(data["hourly_distribution"]) == 24

    def test_get_alerts_returns_200(self, client):
        resp = client.get("/alerts")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_system_devices_returns_200(self, client):
        resp = client.get("/system/devices")
        assert resp.status_code == 200
        assert len(resp.json()) > 0


# ---------------------------------------------------------------------------
# Manual Override
# ---------------------------------------------------------------------------

class TestManualOverride:
    def test_manual_override_with_reason(self, client):
        resp = client.post("/manual/override", json={"reason": "Security drill"})
        assert resp.status_code == 200

    def test_manual_override_default_reason(self, client):
        resp = client.post("/manual/override", json={})
        assert resp.status_code == 200

    def test_manual_override_invalid_body_returns_422(self, client):
        resp = client.post(
            "/manual/override",
            content="not-json",
            headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 422
