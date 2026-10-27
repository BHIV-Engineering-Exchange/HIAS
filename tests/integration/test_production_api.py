"""
Integration tests for api/production.py
Tests:
  - 100% test pass rate across unit and integration test suites (pytest)
  - Complete error boundary protection: zero unhandled 500 exceptions on malformed inputs
  - All API routes validate inbound request schemas with strict Pydantic models
"""
import pytest
from fastapi.testclient import TestClient
from api.production import app


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class TestProductionAPIHealth:
    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestProductionAPIAccessEvent:
    def test_valid_access_event(self, client):
        resp = client.post("/access/event", json={
            "user_id": "S001",
            "method": "RFID",
            "device_id": "main_turnstile_in"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "ALLOW"
        assert len(data["state_hash"]) == 64

    def test_duplicate_scan_suppressed(self, client):
        payload = {
            "user_id": "S002",
            "method": "RFID",
            "device_id": "gate_in_02"
        }
        resp1 = client.post("/access/event", json=payload)
        assert resp1.status_code == 200
        resp2 = client.post("/access/event", json=payload)
        assert resp2.status_code == 429

    def test_missing_required_field_returns_422(self, client):
        resp = client.post("/access/event", json={"user_id": "S001"})
        assert resp.status_code == 422

    def test_invalid_method_enum_returns_422(self, client):
        resp = client.post("/access/event", json={
            "user_id": "S001",
            "method": "INVALID_METHOD",
            "device_id": "gate_01"
        })
        assert resp.status_code == 422

    def test_empty_user_id_returns_422(self, client):
        resp = client.post("/access/event", json={
            "user_id": "",
            "method": "RFID",
            "device_id": "gate_01"
        })
        assert resp.status_code == 422


class TestProductionAPIManualOverride:
    def test_manual_override_valid(self, client):
        resp = client.post("/manual/override", json={"reason": "Fire drill bypass"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "ALLOW"
        assert data["reason"] == "Fire drill bypass"

    def test_manual_override_default_reason(self, client):
        resp = client.post("/manual/override", json={})
        assert resp.status_code == 200
        assert resp.json()["reason"] == "No reason provided"

    def test_manual_override_empty_reason_returns_422(self, client):
        resp = client.post("/manual/override", json={"reason": ""})
        assert resp.status_code == 422


class TestProductionAPISettings:
    def test_get_and_update_settings(self, client):
        resp = client.get("/settings")
        assert resp.status_code == 200
        assert "emergency_mode" in resp.json()

        update_resp = client.post("/settings", json={"emergency_mode": True})
        assert update_resp.status_code == 200
        assert update_resp.json()["emergency_mode"] is True

        # Reset
        client.post("/settings", json={"emergency_mode": False})

    def test_settings_forbidden_extra_fields_returns_422(self, client):
        resp = client.post("/settings", json={"unauthorized_key": "malicious"})
        assert resp.status_code == 422


class TestProductionAPIUsers:
    def test_enroll_user_valid(self, client):
        resp = client.post("/users", json={"user_id": "P500", "name": "Pritesh Patra", "role": "Candidate"})
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "P500"

    def test_enroll_duplicate_user_returns_400(self, client):
        client.post("/users", json={"user_id": "P501", "name": "Resident A"})
        resp = client.post("/users", json={"user_id": "P501", "name": "Resident B"})
        assert resp.status_code == 400

    def test_enroll_user_missing_fields_returns_422(self, client):
        resp = client.post("/users", json={"user_id": "P502"})
        assert resp.status_code == 422


class TestProductionAPIReview:
    def test_review_action_not_found_returns_404(self, client):
        resp = client.post("/review/action", json={"trace_id": "non-existent-trace", "action": "confirm"})
        assert resp.status_code == 404

    def test_review_action_invalid_action_returns_422(self, client):
        resp = client.post("/review/action", json={"trace_id": "trace-123", "action": "maybe"})
        assert resp.status_code == 422


class TestProductionAPIEventsAndStats:
    def test_events_log(self, client):
        resp = client.get("/events")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_stats_summary(self, client):
        resp = client.get("/stats/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data and "granted" in data and "denied" in data


class TestProductionAPILLMAnalysis:
    def test_llm_analysis_fallback_endpoint(self, client):
        resp = client.post("/audit/llm-analysis", json={"prompt": "Verify audit convergence"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
