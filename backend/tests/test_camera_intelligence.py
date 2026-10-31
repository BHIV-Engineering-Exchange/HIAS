"""
Tests for the Camera Intelligence integration endpoint and adapter.

Covers:
  - Integration disabled by default (403)
  - Contract validation (storage.schema.json compliance):
    - trace_id pattern (^HIAS-[0-9]{8}-[a-f0-9]{8}-[0-9]{6}$)
    - timestamp ISO-8601 validation
    - student_id pattern (^[A-Z0-9]{6,10}$) and rejection of UNKNOWN
    - event enum (ENTRY, EXIT)
    - confidence bounds (0.0 - 1.0)
    - status enum (AUTO, REVIEW, REJECT, CORRECTED)
    - source_service enum (confidence_service, human_loop_service)
    - rejection of unknown / extra fields
  - Mapping configuration:
    - empty default mapping behavior
    - parsing comma-separated mapping
    - rejection of malformed mapping entries, empty IDs, duplicate source IDs
    - rejection of unmapped student IDs
    - rejection of mapping to nonexistent HIAS users
  - Storage Service persistence authority:
    - Events forwarded to MongoDB Storage Service (/store-event)
    - No duplicate event written to local HIAS SQLite Event table
    - Accepted events marked REVIEW and broadcast to SSE clients
    - Duplicate trace IDs rejected (409)
    - Storage Service failures handled safely (502 / 503)
    - Failed persistence prevents SSE broadcast
  - Hardware isolation:
    - open_gate() never called under any condition
"""

import pytest
import httpx
from unittest.mock import patch, MagicMock, AsyncMock
from app.models import Direction, Decision, Method
from app.camera_intelligence import parse_student_user_mapping

URL = "/integrations/camera-intelligence/event"


def _valid_payload(**overrides):
    """Return a contract-compliant camera intelligence event payload."""
    base = {
        "trace_id": "HIAS-20261029-abcdef12-000001",
        "timestamp": "2026-10-29T10:00:00Z",
        "student_id": "STU0000001",
        "event": "ENTRY",
        "confidence": 0.95,
        "status": "AUTO",
        "source_service": "confidence_service",
    }
    base.update(overrides)
    return base


# =========================================================================
# 1. Integration disabled by default
# =========================================================================

class TestDisabledIntegration:
    """When CAMERA_INTELLIGENCE_ENABLED is false (default), reject all events."""

    def test_returns_403_when_disabled(self, client):
        response = client.post(URL, json=_valid_payload())
        assert response.status_code == 403
        assert "disabled" in response.json()["detail"].lower()

    def test_gate_not_called_when_disabled(self, client):
        client.post(URL, json=_valid_payload())
        client.mock_open_gate.assert_not_called()


# =========================================================================
# 2. Source Event Contract Validation (storage.schema.json)
# =========================================================================

class TestContractValidation:
    """Payloads must conform strictly to the storage.schema.json contract."""

    def test_missing_required_fields(self, client):
        response = client.post(URL, json={"trace_id": "HIAS-20261029-abcdef12-000001"})
        assert response.status_code == 422

    def test_empty_body(self, client):
        response = client.post(URL, json={})
        assert response.status_code == 422

    def test_confidence_above_one(self, client):
        response = client.post(URL, json=_valid_payload(confidence=1.5))
        assert response.status_code == 422

    def test_confidence_below_zero(self, client):
        response = client.post(URL, json=_valid_payload(confidence=-0.1))
        assert response.status_code == 422

    def test_invalid_timestamp(self, client):
        response = client.post(URL, json=_valid_payload(timestamp="invalid-date"))
        assert response.status_code == 422

    def test_invalid_event_type(self, client):
        response = client.post(URL, json=_valid_payload(event="WALK_THROUGH"))
        assert response.status_code == 422

    def test_invalid_status(self, client):
        response = client.post(URL, json=_valid_payload(status="PENDING"))
        assert response.status_code == 422

    # --- trace_id format tests ---

    def test_invalid_trace_id_too_short(self, client):
        response = client.post(URL, json=_valid_payload(trace_id="HIAS-12345"))
        assert response.status_code == 422

    def test_invalid_trace_id_uppercase_hex(self, client):
        # Contract specifies [a-f0-9]{8} lowercase
        response = client.post(
            URL, json=_valid_payload(trace_id="HIAS-20261029-ABCDEF12-000001")
        )
        assert response.status_code == 422

    def test_invalid_trace_id_wrong_prefix(self, client):
        response = client.post(
            URL, json=_valid_payload(trace_id="GATE-20261029-abcdef12-000001")
        )
        assert response.status_code == 422

    # --- student_id format tests ---

    def test_invalid_student_id_too_short(self, client):
        # S001 is only 4 chars; minimum is 6
        response = client.post(URL, json=_valid_payload(student_id="S001"))
        assert response.status_code == 422

    def test_invalid_student_id_too_long(self, client):
        # Maximum is 10 chars
        response = client.post(URL, json=_valid_payload(student_id="STUDENT12345"))
        assert response.status_code == 422

    def test_invalid_student_id_lowercase(self, client):
        response = client.post(URL, json=_valid_payload(student_id="stu0000001"))
        assert response.status_code == 422

    def test_unknown_student_id_rejected(self, client):
        response = client.post(URL, json=_valid_payload(student_id="UNKNOWN"))
        assert response.status_code == 422

    # --- source_service format tests ---

    def test_invalid_source_service_generic_camera(self, client):
        # Contract requires confidence_service or human_loop_service
        response = client.post(
            URL, json=_valid_payload(source_service="camera-intelligence")
        )
        assert response.status_code == 422

    def test_valid_source_service_human_loop(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            response = client.post(
                URL, json=_valid_payload(source_service="human_loop_service")
            )
            assert response.status_code == 200

    # --- unknown extra fields rejected ---

    def test_reject_unknown_fields(self, client):
        payload = _valid_payload()
        payload["unrecognized_field"] = "unexpected_data"
        response = client.post(URL, json=payload)
        assert response.status_code == 422


# =========================================================================
# 3. Mapping Configuration & User Verification
# =========================================================================

class TestMappingAndIdentity:
    """Mapping configuration rules and HIAS user verification."""

    def test_empty_default_mapping(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            with patch("app.camera_intelligence.STUDENT_USER_MAPPING", {}):
                response = client.post(URL, json=_valid_payload())
                assert response.status_code == 422
                assert "No HIAS user mapping" in response.json()["detail"]

    def test_unmapped_student_id_rejected(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            response = client.post(
                URL, json=_valid_payload(student_id="UNMAPPED99")
            )
            assert response.status_code == 422
            assert "No HIAS user mapping" in response.json()["detail"]

    def test_mapped_nonexistent_hias_user_rejected(self, client):
        # STUNONEX99 is configured in test fixture to map to S999, which is not in the DB
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            response = client.post(
                URL, json=_valid_payload(student_id="STUNONEX99")
            )
            assert response.status_code == 422
            assert "does not exist" in response.json()["detail"]

    def test_parse_student_user_mapping_valid(self):
        result = parse_student_user_mapping("CAM01:S001, CAM02:S002")
        assert result == {"CAM01": "S001", "CAM02": "S002"}

    def test_parse_student_user_mapping_empty(self):
        assert parse_student_user_mapping("") == {}
        assert parse_student_user_mapping("   ") == {}

    def test_parse_student_user_mapping_malformed_missing_colon(self):
        with pytest.raises(ValueError, match="expected 'student_id:user_id'"):
            parse_student_user_mapping("CAM01S001")

    def test_parse_student_user_mapping_empty_id(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            parse_student_user_mapping("CAM01:")

        with pytest.raises(ValueError, match="cannot be empty"):
            parse_student_user_mapping(":S001")

    def test_parse_student_user_mapping_duplicate_source_id(self):
        with pytest.raises(ValueError, match="Duplicate source student_id"):
            parse_student_user_mapping("CAM01:S001, CAM01:S002")


# =========================================================================
# 4. Accepted Audit-Only Events & Persistence Isolation
# =========================================================================

class TestAuditOnlyEvents:
    """Valid events are persisted to Storage Service, not local SQLite."""

    def test_accepted_event_returns_200(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            response = client.post(URL, json=_valid_payload())
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "AUDIT_RECORDED"
            assert data["decision"] == "REVIEW"
            assert data["mapped_user_id"] == "S001"
            assert data["storage_result"]["status"] == "ACCEPTED"
            assert "no physical access" in data["note"].lower()

    def test_audit_event_persisted_to_storage_and_not_sqlite(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            payload = _valid_payload()
            response = client.post(URL, json=payload)
            assert response.status_code == 200

            # 1. Verify forwarded to Storage Service
            client.mock_storage_post.assert_called_once()
            call_kwargs = client.mock_storage_post.call_args[1]
            posted_data = call_kwargs["json"]
            assert posted_data["trace_id"] == payload["trace_id"]
            assert posted_data["student_id"] == payload["student_id"]
            assert posted_data["status"] == "REVIEW"
            assert posted_data["metadata"]["mapped_hias_user_id"] == "S001"
            assert posted_data["metadata"]["audit_only"] is True

            # 2. Verify NOT added to local SQLite database
            events_resp = client.get("/events?limit=100")
            events = events_resp.json()
            cam_events = [e for e in events if e["trace_id"] == payload["trace_id"]]
            assert len(cam_events) == 0

    def test_original_trace_id_preserved(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            trace = "HIAS-20261029-11223344-999999"
            response = client.post(URL, json=_valid_payload(trace_id=trace))
            assert response.status_code == 200
            call_kwargs = client.mock_storage_post.call_args[1]
            assert call_kwargs["json"]["trace_id"] == trace

    def test_exit_event_maps_to_direction_out(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            with patch("app.main.broadcast_event", new_callable=AsyncMock) as mock_broadcast:
                trace = "HIAS-20261029-abcdef12-000002"
                response = client.post(
                    URL,
                    json=_valid_payload(event="EXIT", trace_id=trace),
                )
                assert response.status_code == 200
                mock_broadcast.assert_called_once()
                broadcasted = mock_broadcast.call_args[0][0]
                assert broadcasted.direction == Direction.OUT
                assert broadcasted.trace_id == trace

    def test_entry_event_maps_to_direction_in(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            with patch("app.main.broadcast_event", new_callable=AsyncMock) as mock_broadcast:
                trace = "HIAS-20261029-abcdef12-000003"
                response = client.post(
                    URL,
                    json=_valid_payload(event="ENTRY", trace_id=trace),
                )
                assert response.status_code == 200
                mock_broadcast.assert_called_once()
                broadcasted = mock_broadcast.call_args[0][0]
                assert broadcasted.direction == Direction.IN
                assert broadcasted.trace_id == trace


# =========================================================================
# 5. Storage Service Error Handling & SSE Safeguards
# =========================================================================

class TestStorageServiceErrorHandling:
    """Robust error handling when communicating with the Storage Service."""

    def test_duplicate_returns_409(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            dup_resp = MagicMock()
            dup_resp.status_code = 200
            dup_resp.json.return_value = {
                "status": "REJECTED",
                "reason": "Event with this trace_id already exists",
            }
            client.mock_storage_post.side_effect = None
            client.mock_storage_post.return_value = dup_resp

            payload = _valid_payload(trace_id="HIAS-20261029-abcdef12-000004")
            response = client.post(URL, json=payload)
            assert response.status_code == 409
            assert "Duplicate" in response.json()["detail"]

    def test_storage_rejected_non_duplicate_returns_502(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            rej_resp = MagicMock()
            rej_resp.status_code = 200
            rej_resp.json.return_value = {
                "status": "REJECTED",
                "reason": "Schema validation failed: confidence out of range",
            }
            client.mock_storage_post.side_effect = None
            client.mock_storage_post.return_value = rej_resp

            response = client.post(URL, json=_valid_payload())
            assert response.status_code == 502
            data = response.json()["detail"]
            assert data["error"] == "Storage Service rejected event"
            assert "confidence out of range" in data["reason"]

    def test_storage_http_error_returns_502(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            err_resp = MagicMock()
            err_resp.status_code = 500
            err_resp.json.return_value = {"error": "Internal Server Error"}
            client.mock_storage_post.side_effect = None
            client.mock_storage_post.return_value = err_resp

            response = client.post(URL, json=_valid_payload())
            assert response.status_code == 502
            data = response.json()["detail"]
            assert data["error"] == "Storage Service HTTP error"
            assert data["status_code"] == 500

    def test_storage_timeout_returns_503(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            client.mock_storage_post.side_effect = httpx.TimeoutException("Connection timed out")

            response = client.post(URL, json=_valid_payload())
            assert response.status_code == 503
            data = response.json()["detail"]
            assert data["error"] == "Storage Service timeout"

    def test_storage_unreachable_returns_503(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            client.mock_storage_post.side_effect = httpx.ConnectError("Connection refused")

            response = client.post(URL, json=_valid_payload())
            assert response.status_code == 503
            data = response.json()["detail"]
            assert data["error"] == "Storage Service unavailable"

    def test_accepted_event_triggers_sse_broadcast(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            with patch("app.main.broadcast_event", new_callable=AsyncMock) as mock_broadcast:
                response = client.post(URL, json=_valid_payload())
                assert response.status_code == 200
                mock_broadcast.assert_called_once()
                event = mock_broadcast.call_args[0][0]
                assert event.trace_id == "HIAS-20261029-abcdef12-000001"
                assert event.decision == Decision.REVIEW
                assert event.method == Method.FACE
                assert event.user_id == "S001"

    def test_failed_persistence_prevents_sse_broadcast(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            with patch("app.main.broadcast_event", new_callable=AsyncMock) as mock_broadcast:
                client.mock_storage_post.side_effect = httpx.TimeoutException("Timeout")
                response = client.post(URL, json=_valid_payload())
                assert response.status_code == 503
                mock_broadcast.assert_not_called()


# =========================================================================
# 6. open_gate() is NEVER called
# =========================================================================

class TestNoGateActivation:
    """Camera intelligence events must never trigger physical gate access."""

    def test_gate_not_called_on_accepted_event(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            client.post(URL, json=_valid_payload())
            client.mock_open_gate.assert_not_called()

    def test_gate_not_called_on_rejected_event(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            client.post(URL, json=_valid_payload(student_id="UNMAPPED99"))
            client.mock_open_gate.assert_not_called()

    def test_gate_not_called_on_disabled(self, client):
        client.post(URL, json=_valid_payload())
        client.mock_open_gate.assert_not_called()

    def test_gate_not_called_on_duplicate(self, client):
        with patch("app.camera_intelligence.CAMERA_INTELLIGENCE_ENABLED", True):
            dup_resp = MagicMock()
            dup_resp.status_code = 200
            dup_resp.json.return_value = {
                "status": "REJECTED",
                "reason": "Duplicate trace_id",
            }
            client.mock_storage_post.side_effect = None
            client.mock_storage_post.return_value = dup_resp

            payload = _valid_payload(trace_id="HIAS-20261029-abcdef12-000005")
            client.post(URL, json=payload)
            client.mock_open_gate.assert_not_called()
