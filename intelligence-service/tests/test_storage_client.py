import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure intelligence-service root is in sys.path
INTELLIGENCE_ROOT = str(Path(__file__).resolve().parent.parent)
if INTELLIGENCE_ROOT not in sys.path:
    sys.path.insert(0, INTELLIGENCE_ROOT)

import pytest
import requests
from fastapi.testclient import TestClient

from app.entry_exit_logic import EntryExitEngine, parse_timestamp
from app.main import app, intelligence_service, storage_client
from app.service import IntelligenceService
from app.storage_client import StorageClient

SAMPLE_STORAGE_EVENT = {
    "trace_id": "HIAS-20261024-a1b2c3d4-000001",
    "timestamp": "2026-10-24T08:15:30.123Z",
    "student_id": "STU001001",
    "event": "ENTRY",
    "confidence": 0.95,
    "status": "AUTO",
    "source_service": "confidence_service",
    "camera_id": "GATE-MAIN",
    "zone": "GATE_MAIN",
    "anomaly_flags": [],
    "metadata": {
        "correction_applied": False,
        "original_student_id": "STU001001",
        "operator_id": None,
        "correction_notes": "",
    },
}

SAMPLE_RECOGNITION_EVENT = {
    "trace_id": "HIAS-20261024-a1b2c3d4-000001",
    "timestamp": "2026-10-24T08:15:30.123Z",
    "student_id": "STU001001",
    "confidence": 0.95,
    "face_detected": True,
}


# ============================================================================
# 1. StorageClient Config & store_event Tests
# ============================================================================


def test_storage_client_defaults():
    """Verify default base URL and timeout."""
    client = StorageClient()
    assert client.base_url == "http://127.0.0.1:8005"
    assert client.timeout == 5.0


def test_storage_client_env_config(monkeypatch):
    """Verify configuration via environment variables."""
    monkeypatch.setenv("STORAGE_SERVICE_URL", "http://storage.internal:9000/")
    monkeypatch.setenv("STORAGE_REQUEST_TIMEOUT", "12.5")
    client = StorageClient()
    assert client.base_url == "http://storage.internal:9000"
    assert client.timeout == 12.5


def test_storage_client_accepted_response():
    """Verify handling when Storage accepts an event."""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "trace_id": SAMPLE_STORAGE_EVENT["trace_id"],
        "event_id": "evt-uuid-12345",
        "hash": "a" * 64,
        "prev_hash": "0" * 64,
        "status": "ACCEPTED",
        "reason": None,
    }
    mock_session.post.return_value = mock_response

    client = StorageClient(session=mock_session)
    result = client.store_event(SAMPLE_STORAGE_EVENT)

    assert result["success"] is True
    assert result["status"] == "ACCEPTED"
    assert result["event_id"] == "evt-uuid-12345"
    assert result["hash"] == "a" * 64
    assert result["trace_id"] == SAMPLE_STORAGE_EVENT["trace_id"]
    mock_session.post.assert_called_once()


def test_storage_client_rejected_response():
    """Verify handling when Storage returns REJECTED (e.g. duplicate trace_id)."""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "trace_id": SAMPLE_STORAGE_EVENT["trace_id"],
        "event_id": "",
        "hash": "",
        "prev_hash": None,
        "status": "REJECTED",
        "reason": "Event with this trace_id already exists (append-only constraint)",
    }
    mock_session.post.return_value = mock_response

    client = StorageClient(session=mock_session)
    result = client.store_event(SAMPLE_STORAGE_EVENT)

    assert result["success"] is False
    assert result["status"] == "REJECTED"
    assert "already exists" in result["reason"]
    assert result["trace_id"] == SAMPLE_STORAGE_EVENT["trace_id"]


def test_storage_client_http_error():
    """Verify handling of non-200 HTTP response codes on store_event."""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.text = '{"detail": "Storage service not initialized"}'
    mock_session.post.return_value = mock_response

    client = StorageClient(session=mock_session)
    result = client.store_event(SAMPLE_STORAGE_EVENT)

    assert result["success"] is False
    assert result["status"] == "HTTP_ERROR"
    assert result["http_status"] == 503
    assert "503" in result["reason"]


def test_storage_client_timeout():
    """Verify handling when Storage request times out on store_event."""
    mock_session = MagicMock()
    mock_session.post.side_effect = requests.exceptions.Timeout("Connection timed out after 5s")

    client = StorageClient(session=mock_session)
    result = client.store_event(SAMPLE_STORAGE_EVENT)

    assert result["success"] is False
    assert result["status"] == "TIMEOUT"
    assert "timed out" in result["reason"].lower()


def test_storage_client_unreachable():
    """Verify handling when Storage service is unreachable on store_event."""
    mock_session = MagicMock()
    mock_session.post.side_effect = requests.exceptions.ConnectionError("Connection refused to port 8005")

    client = StorageClient(session=mock_session)
    result = client.store_event(SAMPLE_STORAGE_EVENT)

    assert result["success"] is False
    assert result["status"] == "UNREACHABLE"
    assert "unreachable" in result["reason"].lower()


def test_storage_client_skips_unknown_student_id():
    """Verify events with UNKNOWN student_id are safely skipped and not posted to Storage."""
    mock_session = MagicMock()
    client = StorageClient(session=mock_session)

    unknown_event = {**SAMPLE_STORAGE_EVENT, "student_id": "UNKNOWN"}
    result = client.store_event(unknown_event)

    assert result["success"] is False
    assert result["status"] == "SKIPPED"
    assert "unknown" in result["reason"].lower()
    mock_session.post.assert_not_called()


def test_storage_client_skips_reject_status():
    """Verify events with REJECT status are safely skipped and not posted to Storage."""
    mock_session = MagicMock()
    client = StorageClient(session=mock_session)

    reject_event = {**SAMPLE_STORAGE_EVENT, "status": "REJECT"}
    result = client.store_event(reject_event)

    assert result["success"] is False
    assert result["status"] == "SKIPPED"
    assert "reject" in result["reason"].lower()
    mock_session.post.assert_not_called()


# ============================================================================
# 2. StorageClient.fetch_by_student Tests
# ============================================================================


def test_storage_client_fetch_by_student_success():
    """Verify fetch_by_student successfully returns event history list."""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "events": [
            {
                "trace_id": "HIAS-20261024-a1b2c3d4-000001",
                "student_id": "STU001001",
                "event": "ENTRY",
                "confidence": 0.95,
                "status": "AUTO",
                "timestamp": "2026-10-24T08:15:30.123Z",
                "hash": "a" * 64,
                "prev_hash": "0" * 64,
            }
        ],
        "total_count": 1,
    }
    mock_session.get.return_value = mock_response

    client = StorageClient(session=mock_session)
    result = client.fetch_by_student("STU001001")

    assert result["ok"] is True
    assert result["status"] == "OK"
    assert len(result["events"]) == 1
    assert result["events"][0]["event"] == "ENTRY"
    assert result["total_count"] == 1
    mock_session.get.assert_called_once_with(
        "http://127.0.0.1:8005/fetch-by-student",
        params={"student_id": "STU001001"},
        timeout=5.0,
    )


def test_storage_client_fetch_by_student_empty_history():
    """Verify fetch_by_student handles a student with zero historical events cleanly."""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"events": [], "total_count": 0}
    mock_session.get.return_value = mock_response

    client = StorageClient(session=mock_session)
    result = client.fetch_by_student("STU001001")

    assert result["ok"] is True
    assert result["status"] == "OK"
    assert result["events"] == []
    assert result["total_count"] == 0


def test_storage_client_fetch_by_student_timeout():
    """Verify fetch_by_student handles timeout explicitly."""
    mock_session = MagicMock()
    mock_session.get.side_effect = requests.exceptions.Timeout("Read timed out after 5.0s")

    client = StorageClient(session=mock_session)
    result = client.fetch_by_student("STU001001")

    assert result["ok"] is False
    assert result["status"] == "TIMEOUT"
    assert "timed out" in result["error"].lower()


def test_storage_client_fetch_by_student_unreachable():
    """Verify fetch_by_student handles connection failure explicitly."""
    mock_session = MagicMock()
    mock_session.get.side_effect = requests.exceptions.ConnectionError("Connection refused")

    client = StorageClient(session=mock_session)
    result = client.fetch_by_student("STU001001")

    assert result["ok"] is False
    assert result["status"] == "UNREACHABLE"
    assert "unreachable" in result["error"].lower()


def test_storage_client_fetch_by_student_http_error():
    """Verify fetch_by_student handles non-200 HTTP error explicitly."""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = '{"detail": "Internal database error"}'
    mock_session.get.return_value = mock_response

    client = StorageClient(session=mock_session)
    result = client.fetch_by_student("STU001001")

    assert result["ok"] is False
    assert result["status"] == "HTTP_ERROR"
    assert result["http_status"] == 500
    assert "500" in result["error"]


def test_storage_client_fetch_by_student_malformed_json():
    """Verify fetch_by_student handles invalid JSON payload explicitly."""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError("Invalid JSON string")
    mock_session.get.return_value = mock_response

    client = StorageClient(session=mock_session)
    result = client.fetch_by_student("STU001001")

    assert result["ok"] is False
    assert result["status"] == "INVALID_RESPONSE"
    assert "invalid json" in result["error"].lower()


def test_storage_client_fetch_by_student_missing_events_field():
    """Verify fetch_by_student handles response missing 'events' list explicitly."""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"something_else": 123}
    mock_session.get.return_value = mock_response

    client = StorageClient(session=mock_session)
    result = client.fetch_by_student("STU001001")

    assert result["ok"] is False
    assert result["status"] == "INVALID_RESPONSE"
    assert "missing valid 'events'" in result["error"]


def test_storage_client_fetch_by_student_invalid_id():
    """Verify fetch_by_student rejects empty student ID without network call."""
    mock_session = MagicMock()
    client = StorageClient(session=mock_session)

    res1 = client.fetch_by_student("")
    assert res1["ok"] is False
    assert res1["status"] == "INVALID_STUDENT_ID"

    res2 = client.fetch_by_student(None)  # type: ignore[arg-type]
    assert res2["ok"] is False
    assert res2["status"] == "INVALID_STUDENT_ID"
    mock_session.get.assert_not_called()


# ============================================================================
# 3. EntryExitEngine.restore_state_from_history Tests
# ============================================================================


def test_engine_restore_entry_infers_exit_after_restart():
    """State survival requirement: A student whose previous event was ENTRY is inferred as EXIT after restart."""
    engine = EntryExitEngine()

    persisted_history = [
        {
            "trace_id": "HIAS-20261024-a1b2c3d4-000001",
            "student_id": "STU001001",
            "event": "ENTRY",
            "confidence": 0.95,
            "status": "AUTO",
            "timestamp": "2026-10-24T08:00:00Z",
        }
    ]

    # Restore state from persisted event
    restored = engine.restore_state_from_history("STU001001", persisted_history)
    assert restored is not None
    assert restored.last_event == "ENTRY"
    assert restored.last_trace_id == "HIAS-20261024-a1b2c3d4-000001"

    # Interpret new recognition event (1 hour later)
    result = engine.interpret(
        trace_id="HIAS-20261024-a1b2c3d4-000002",
        student_id="STU001001",
        timestamp="2026-10-24T09:00:00Z",
    )

    assert result["event"] == "EXIT"
    assert result["is_duplicate"] is False
    assert engine.get_state("STU001001").last_event == "EXIT"


def test_engine_restore_exit_infers_entry_after_restart():
    """State survival requirement: A student whose previous event was EXIT is inferred as ENTRY after restart."""
    engine = EntryExitEngine()

    persisted_history = [
        {
            "trace_id": "HIAS-20261024-a1b2c3d4-000002",
            "student_id": "STU001001",
            "event": "EXIT",
            "confidence": 0.95,
            "status": "AUTO",
            "timestamp": "2026-10-24T12:00:00Z",
        },
        {
            "trace_id": "HIAS-20261024-a1b2c3d4-000001",
            "student_id": "STU001001",
            "event": "ENTRY",
            "confidence": 0.95,
            "status": "AUTO",
            "timestamp": "2026-10-24T08:00:00Z",
        },
    ]

    restored = engine.restore_state_from_history("STU001001", persisted_history)
    assert restored is not None
    assert restored.last_event == "EXIT"

    # Interpret new recognition event (next morning)
    result = engine.interpret(
        trace_id="HIAS-20261024-a1b2c3d4-000003",
        student_id="STU001001",
        timestamp="2026-10-25T08:00:00Z",
    )

    assert result["event"] == "ENTRY"
    assert engine.get_state("STU001001").last_event == "ENTRY"


def test_engine_restore_ignores_reject_and_review_unconfirmed_statuses():
    """Verification requirement: REJECT and REVIEW unconfirmed events are not treated as confirmed attendance."""
    engine = EntryExitEngine()

    persisted_history = [
        {
            "trace_id": "HIAS-20261024-a1b2c3d4-000003",
            "student_id": "STU001001",
            "event": "EXIT",
            "confidence": 0.50,
            "status": "REJECT",
            "timestamp": "2026-10-24T10:00:00Z",
        },
        {
            "trace_id": "HIAS-20261024-a1b2c3d4-000002",
            "student_id": "STU001001",
            "event": "EXIT",
            "confidence": 0.72,
            "status": "REVIEW",
            "timestamp": "2026-10-24T09:30:00Z",
        },
        {
            "trace_id": "HIAS-20261024-a1b2c3d4-000001",
            "student_id": "STU001001",
            "event": "ENTRY",
            "confidence": 0.96,
            "status": "AUTO",
            "timestamp": "2026-10-24T08:00:00Z",
        },
    ]

    restored = engine.restore_state_from_history("STU001001", persisted_history)
    assert restored is not None
    # Must restore from the confirmed AUTO ENTRY, ignoring REJECT and REVIEW
    assert restored.last_event == "ENTRY"
    assert restored.last_trace_id == "HIAS-20261024-a1b2c3d4-000001"

    # Next event infers EXIT based on confirmed ENTRY
    result = engine.interpret(
        trace_id="HIAS-20261024-a1b2c3d4-000004",
        student_id="STU001001",
        timestamp="2026-10-24T11:00:00Z",
    )
    assert result["event"] == "EXIT"


def test_engine_restore_equal_timestamps_deterministic_ordering():
    """Requirement: Equal timestamps handled deterministically; CORRECTED event inserted later takes precedence."""
    engine = EntryExitEngine()

    same_timestamp = "2026-10-24T08:00:00Z"
    persisted_history = [
        # Index 0: Appended later in Storage by operator correction
        {
            "trace_id": "HIAS-20261024-a1b2c3d4-000002",
            "student_id": "STU001001",
            "event": "EXIT",
            "confidence": 1.0,
            "status": "CORRECTED",
            "timestamp": same_timestamp,
        },
        # Index 1: Appended earlier in Storage
        {
            "trace_id": "HIAS-20261024-a1b2c3d4-000001",
            "student_id": "STU001001",
            "event": "ENTRY",
            "confidence": 0.95,
            "status": "AUTO",
            "timestamp": same_timestamp,
        },
    ]

    restored = engine.restore_state_from_history("STU001001", persisted_history)
    assert restored is not None
    assert restored.last_event == "EXIT"
    assert restored.last_trace_id == "HIAS-20261024-a1b2c3d4-000002"

    result = engine.interpret(
        trace_id="HIAS-20261024-a1b2c3d4-000003",
        student_id="STU001001",
        timestamp="2026-10-24T09:00:00Z",
    )
    assert result["event"] == "ENTRY"


def test_engine_restore_duplicate_trace_ids_deterministic():
    """Requirement: Duplicate trace IDs are handled deterministically without errors."""
    engine = EntryExitEngine()

    persisted_history = [
        {
            "trace_id": "HIAS-20261024-a1b2c3d4-000001",
            "student_id": "STU001001",
            "event": "ENTRY",
            "confidence": 0.95,
            "status": "AUTO",
            "timestamp": "2026-10-24T08:00:00Z",
        },
        {
            "trace_id": "HIAS-20261024-a1b2c3d4-000001",  # Duplicate trace_id
            "student_id": "STU001001",
            "event": "ENTRY",
            "confidence": 0.95,
            "status": "AUTO",
            "timestamp": "2026-10-24T08:00:00Z",
        },
    ]

    restored = engine.restore_state_from_history("STU001001", persisted_history)
    assert restored is not None
    assert restored.last_event == "ENTRY"
    assert restored.last_trace_id == "HIAS-20261024-a1b2c3d4-000001"


def test_engine_restore_empty_history_defaults_to_entry():
    """Requirement: Empty history resets student state and defaults to ENTRY on first recognition."""
    engine = EntryExitEngine()

    restored = engine.restore_state_from_history("STU001001", [])
    assert restored is None
    assert engine.get_state("STU001001") is None

    result = engine.interpret(
        trace_id="HIAS-20261024-a1b2c3d4-000001",
        student_id="STU001001",
        timestamp="2026-10-24T08:00:00Z",
    )
    assert result["event"] == "ENTRY"


def test_engine_restore_duplicate_window_does_not_advance_state():
    """Requirement: Rapid repeated detections within window (<=10s) do not advance state."""
    engine = EntryExitEngine(duplicate_window_seconds=10)

    persisted_history = [
        {
            "trace_id": "HIAS-20261024-a1b2c3d4-000001",
            "student_id": "STU001001",
            "event": "ENTRY",
            "confidence": 0.95,
            "status": "AUTO",
            "timestamp": "2026-10-24T08:00:00Z",
        }
    ]
    engine.restore_state_from_history("STU001001", persisted_history)

    # Rapid detection 4 seconds later
    result = engine.interpret(
        trace_id="HIAS-20261024-a1b2c3d4-000002",
        student_id="STU001001",
        timestamp="2026-10-24T08:00:04Z",
    )

    assert result["is_duplicate"] is True
    assert "RAPID_MULTIPLE_ENTRIES" in result["anomaly_flags"]
    assert "DUPLICATE_ENTRY" in result["anomaly_flags"]

    # State must NOT have advanced to the duplicate event
    state = engine.get_state("STU001001")
    assert state.last_trace_id == "HIAS-20261024-a1b2c3d4-000001"
    assert state.last_timestamp == parse_timestamp("2026-10-24T08:00:00Z")


# ============================================================================
# 4. Intelligence API (/process) End-to-End & Recovery Integration Tests
# ============================================================================


def test_process_endpoint_accepted():
    """Verify /process endpoint passes storage_result on ACCEPTED storage."""
    client = TestClient(app)

    with patch.object(storage_client, "fetch_by_student") as mock_fetch, patch.object(
        storage_client, "store_event"
    ) as mock_store:
        mock_fetch.return_value = {"ok": True, "status": "OK", "events": []}
        mock_store.return_value = {
            "success": True,
            "status": "ACCEPTED",
            "event_id": "evt-auto-12345",
            "hash": "b" * 64,
            "prev_hash": "a" * 64,
            "trace_id": SAMPLE_RECOGNITION_EVENT["trace_id"],
        }

        response = client.post(
            "/process",
            json={
                "recognition_event": SAMPLE_RECOGNITION_EVENT,
                "context": {"camera_id": "GATE-MAIN", "zone": "GATE_MAIN"},
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert "intelligence_event" in data
        assert "confidence_event" in data
        assert "storage_event" in data
        assert "final_event" in data
        assert "status" in data
        assert data["final_event"]["status"] == "AUTO"

        assert "storage_result" in data
        assert data["storage_result"]["success"] is True
        assert data["storage_result"]["status"] == "ACCEPTED"
        assert data["storage_result"]["event_id"] == "evt-auto-12345"

        mock_fetch.assert_called_once_with("STU001001")
        mock_store.assert_called_once()


def test_process_endpoint_rejected():
    """Verify /process endpoint handles Storage REJECTED without failing the process response."""
    client = TestClient(app)

    with patch.object(storage_client, "fetch_by_student") as mock_fetch, patch.object(
        storage_client, "store_event"
    ) as mock_store:
        mock_fetch.return_value = {"ok": True, "status": "OK", "events": []}
        mock_store.return_value = {
            "success": False,
            "status": "REJECTED",
            "reason": "Event with this trace_id already exists",
            "trace_id": SAMPLE_RECOGNITION_EVENT["trace_id"],
        }

        response = client.post(
            "/process",
            json={
                "recognition_event": SAMPLE_RECOGNITION_EVENT,
                "context": {"camera_id": "GATE-MAIN", "zone": "GATE_MAIN"},
            },
        )

        assert response.status_code == 502
        data = response.json()
        assert data["error"] == "STORAGE_PERSISTENCE_FAILED"
        assert data["message"] == "Intelligence event could not be persisted."
        assert data["storage_result"]["success"] is False
        assert data["storage_result"]["status"] == "REJECTED"
        assert data["storage_result"]["reason"] == (
            "Event with this trace_id already exists"
        )
        # Preserve event details for audit and troubleshooting.
        assert "intelligence_event" in data
        assert "confidence_event" in data
        assert "final_event" in data
        mock_store.assert_called_once()


def test_process_endpoint_storage_unreachable_on_store():
    """Verify /process endpoint handles unreachable Storage on store_event cleanly."""
    client = TestClient(app)

    with patch.object(storage_client, "fetch_by_student") as mock_fetch, patch.object(
        storage_client, "store_event"
    ) as mock_store:
        mock_fetch.return_value = {"ok": True, "status": "OK", "events": []}
        mock_store.return_value = {
            "success": False,
            "status": "UNREACHABLE",
            "reason": "Storage service unreachable at http://127.0.0.1:8005",
            "trace_id": SAMPLE_RECOGNITION_EVENT["trace_id"],
        }

        response = client.post(
            "/process",
            json={
                "recognition_event": SAMPLE_RECOGNITION_EVENT,
                "context": {"camera_id": "GATE-MAIN", "zone": "GATE_MAIN"},
            },
        )

        assert response.status_code == 503
        data = response.json()
        assert data["error"] == "STORAGE_PERSISTENCE_FAILED"
        assert data["storage_result"]["success"] is False
        assert data["storage_result"]["status"] == "UNREACHABLE"
        assert "Storage service unreachable" in data["storage_result"]["reason"]
        # Event details must remain available even when storage is down.
        assert "intelligence_event" in data
        assert "confidence_event" in data
        assert "final_event" in data
        mock_store.assert_called_once()


def test_process_endpoint_unknown_identity_skips_storage():
    """Verify unknown identity recognition skips storage recovery and storage write."""
    client = TestClient(app)

    with patch.object(storage_client, "fetch_by_student") as mock_fetch, patch.object(
        storage_client, "store_event"
    ) as mock_store:
        mock_store.return_value = {
            "success": False,
            "status": "SKIPPED",
            "reason": "Cannot store event with unknown student_id",
            "trace_id": "HIAS-20261024-a1b2c3d4-000002",
        }

        unknown_event = {
            "trace_id": "HIAS-20261024-a1b2c3d4-000002",
            "timestamp": "2026-10-24T08:15:30.123Z",
            "student_id": "UNKNOWN",
            "confidence": 0.50,
            "face_detected": True,
        }

        response = client.post(
            "/process",
            json={"recognition_event": unknown_event, "context": {"camera_id": "GATE-MAIN"}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["final_event"]["status"] == "REJECT"
        assert data["final_event"]["student_id"] == "UNKNOWN"

        # fetch_by_student must NOT have been called for UNKNOWN student
        mock_fetch.assert_not_called()
        assert data["storage_result"]["status"] == "SKIPPED"


def test_process_endpoint_state_survives_restart_alternating_entry_exit():
    """
    Convergence requirement test:
    Verify state survives process restart. A student's previous ENTRY in Storage causes
    the next recognition event to be inferred as EXIT after service restart.
    """
    client = TestClient(app)

    # Simulate restart: clear in-memory engine state
    intelligence_service.engine.clear_state()

    persisted_entry = {
        "trace_id": "HIAS-20261024-a1b2c3d4-000001",
        "student_id": "STU001001",
        "event": "ENTRY",
        "confidence": 0.95,
        "status": "AUTO",
        "timestamp": "2026-10-24T08:00:00Z",
    }

    with patch.object(storage_client, "fetch_by_student") as mock_fetch, patch.object(
        storage_client, "store_event"
    ) as mock_store:
        mock_fetch.return_value = {
            "ok": True,
            "status": "OK",
            "events": [persisted_entry],
            "total_count": 1,
        }
        mock_store.return_value = {
            "success": True,
            "status": "ACCEPTED",
            "event_id": "evt-exit-12345",
            "hash": "c" * 64,
            "prev_hash": "b" * 64,
            "trace_id": "HIAS-20261024-a1b2c3d4-000002",
        }

        exit_recognition_event = {
            "trace_id": "HIAS-20261024-a1b2c3d4-000002",
            "timestamp": "2026-10-24T17:00:00Z",
            "student_id": "STU001001",
            "confidence": 0.95,
            "face_detected": True,
        }

        response = client.post(
            "/process",
            json={"recognition_event": exit_recognition_event, "context": {"camera_id": "GATE-MAIN"}},
        )

        assert response.status_code == 200
        data = response.json()

        # Previous was ENTRY -> recovered state makes current event EXIT
        assert data["final_event"]["event"] == "EXIT"
        assert data["storage_event"]["event"] == "EXIT"
        assert data["storage_result"]["status"] == "ACCEPTED"


def test_process_endpoint_storage_unavailable_returns_503_and_prevents_access():
    """
    Requirement 8:
    If Storage is unavailable during state recovery, do not silently pretend state recovery
    succeeded or default to fresh ENTRY. Return explicit 503 error preventing unsafe access.
    """
    client = TestClient(app)

    with patch.object(storage_client, "fetch_by_student") as mock_fetch:
        mock_fetch.return_value = {
            "ok": False,
            "status": "UNREACHABLE",
            "error": "Storage service unreachable at http://127.0.0.1:8005: connection refused",
            "student_id": "STU001001",
        }

        response = client.post(
            "/process",
            json={
                "recognition_event": SAMPLE_RECOGNITION_EVENT,
                "context": {"camera_id": "GATE-MAIN"},
            },
        )

        assert response.status_code == 503
        data = response.json()
        assert data["error_code"] == "ERR_STORAGE_UNAVAILABLE"
        assert data["error_type"] == "SERVICE_UNAVAILABLE"
        assert data["severity"] == "HIGH"
        assert "storage recovery failed" in data["error_message"].lower()


def test_process_endpoint_storage_timeout_returns_503_and_prevents_access():
    """
    Requirement 8:
    If Storage times out during state recovery, return explicit 503 error preventing unsafe access.
    """
    client = TestClient(app)

    with patch.object(storage_client, "fetch_by_student") as mock_fetch:
        mock_fetch.return_value = {
            "ok": False,
            "status": "TIMEOUT",
            "error": "Storage request timed out after 5.0s",
            "student_id": "STU001001",
        }

        response = client.post(
            "/process",
            json={
                "recognition_event": SAMPLE_RECOGNITION_EVENT,
                "context": {"camera_id": "GATE-MAIN"},
            },
        )

        assert response.status_code == 503
        data = response.json()
        assert data["error_code"] == "ERR_STORAGE_UNAVAILABLE"
        assert data["error_type"] == "TIMEOUT"
        assert data["severity"] == "HIGH"


# ============================================================================
# 5. Confidence-Gated State Management Regression Tests
# ============================================================================


def test_low_confidence_event_does_not_update_student_state():
    """Verify that a low-confidence recognition event (<0.70, REJECT) does not update state."""
    service = IntelligenceService()
    event = {
        "trace_id": "HIAS-20261024-a1b2c3d4-000010",
        "timestamp": "2026-10-24T08:15:30.123Z",
        "student_id": "STU001001",
        "confidence": 0.55,
        "face_detected": True,
    }
    result = service.process(event)
    assert result["ok"] is True
    assert result["status"]["status"] == "REJECT"
    assert service.engine.get_state("STU001001") is None


def test_review_event_does_not_update_student_state():
    """Verify that a REVIEW status recognition event (e.g. confidence 0.75) does not update state."""
    service = IntelligenceService()
    event = {
        "trace_id": "HIAS-20261024-a1b2c3d4-000011",
        "timestamp": "2026-10-24T08:15:30.123Z",
        "student_id": "STU001001",
        "confidence": 0.75,
        "face_detected": True,
    }
    result = service.process(event)
    assert result["ok"] is True
    assert result["status"]["status"] == "REVIEW"
    assert service.engine.get_state("STU001001") is None


def test_reject_event_does_not_update_student_state():
    """Verify that REJECT events (e.g. UNKNOWN identity or low confidence) do not update state."""
    service = IntelligenceService()
    unknown_event = {
        "trace_id": "HIAS-20261024-a1b2c3d4-000012",
        "timestamp": "2026-10-24T08:15:30.123Z",
        "student_id": "UNKNOWN",
        "confidence": 0.95,
        "face_detected": True,
    }
    result = service.process(unknown_event)
    assert result["ok"] is True
    assert result["status"]["status"] == "REJECT"
    assert service.engine.get_state("UNKNOWN") is None


def test_auto_event_correctly_updates_student_state():
    """Verify that high-confidence AUTO event correctly commits and updates student state."""
    service = IntelligenceService()
    event = {
        "trace_id": "HIAS-20261024-a1b2c3d4-000013",
        "timestamp": "2026-10-24T08:15:30.123Z",
        "student_id": "STU001001",
        "confidence": 0.95,
        "face_detected": True,
    }
    result = service.process(event)
    assert result["ok"] is True
    assert result["status"]["status"] == "AUTO"
    state = service.engine.get_state("STU001001")
    assert state is not None
    assert state.last_event == "ENTRY"
    assert state.last_trace_id == "HIAS-20261024-a1b2c3d4-000013"
    assert state.last_timestamp == parse_timestamp("2026-10-24T08:15:30.123Z")


def test_duplicate_event_does_not_update_student_state():
    """Verify that a duplicate event within the window does not advance or update student state."""
    service = IntelligenceService(entry_exit_engine=EntryExitEngine(duplicate_window_seconds=10))
    event1 = {
        "trace_id": "HIAS-20261024-a1b2c3d4-000014",
        "timestamp": "2026-10-24T08:00:00.000Z",
        "student_id": "STU001001",
        "confidence": 0.95,
        "face_detected": True,
    }
    result1 = service.process(event1)
    assert result1["ok"] is True
    assert result1["status"]["status"] == "AUTO"
    state1 = service.engine.get_state("STU001001")
    assert state1.last_trace_id == "HIAS-20261024-a1b2c3d4-000014"

    # Duplicate 4 seconds later with high confidence
    event2 = {
        "trace_id": "HIAS-20261024-a1b2c3d4-000015",
        "timestamp": "2026-10-24T08:00:04.000Z",
        "student_id": "STU001001",
        "confidence": 0.95,
        "face_detected": True,
    }
    result2 = service.process(event2)
    assert result2["ok"] is True
    assert result2["status"]["status"] == "REJECT"  # duplicate routed as REJECT

    # State must still reference event1, not event2
    state2 = service.engine.get_state("STU001001")
    assert state2.last_trace_id == "HIAS-20261024-a1b2c3d4-000014"
    assert state2.last_timestamp == parse_timestamp("2026-10-24T08:00:00.000Z")


def test_subsequent_high_confidence_event_infers_from_last_confirmed_not_rejected():
    """
    Core integrity requirement:
    A student has confirmed ENTRY. A subsequent REJECT/REVIEW event attempts an EXIT
    inference but is rejected/reviewed and thus must NOT mutate state.
    A later high-confidence AUTO event must infer EXIT from the confirmed ENTRY,
    not flip back to ENTRY as if the rejected event had been committed.
    """
    service = IntelligenceService()

    # Step 1: Confirmed ENTRY (AUTO)
    entry_event = {
        "trace_id": "HIAS-20261024-a1b2c3d4-000020",
        "timestamp": "2026-10-24T08:00:00.000Z",
        "student_id": "STU001001",
        "confidence": 0.95,
        "face_detected": True,
    }
    res_entry = service.process(entry_event)
    assert res_entry["status"]["status"] == "AUTO"
    assert res_entry["final_event"]["event"] == "ENTRY"
    assert service.engine.get_state("STU001001").last_event == "ENTRY"

    # Step 2: Low-confidence detection 1 hour later (confidence 0.50 -> REJECT)
    # The engine interprets this as EXIT, but routing rejects it.
    rejected_event = {
        "trace_id": "HIAS-20261024-a1b2c3d4-000021",
        "timestamp": "2026-10-24T09:00:00.000Z",
        "student_id": "STU001001",
        "confidence": 0.50,
        "face_detected": True,
    }
    res_reject = service.process(rejected_event)
    assert res_reject["status"]["status"] == "REJECT"
    # State MUST NOT be updated to EXIT: still ENTRY from event 000020
    assert service.engine.get_state("STU001001").last_event == "ENTRY"
    assert service.engine.get_state("STU001001").last_trace_id == "HIAS-20261024-a1b2c3d4-000020"

    # Step 3: Review-band detection 30 minutes later (confidence 0.75 -> REVIEW)
    review_event = {
        "trace_id": "HIAS-20261024-a1b2c3d4-000022",
        "timestamp": "2026-10-24T09:30:00.000Z",
        "student_id": "STU001001",
        "confidence": 0.75,
        "face_detected": True,
    }
    res_review = service.process(review_event)
    assert res_review["status"]["status"] == "REVIEW"
    # State MUST STILL be ENTRY from event 000020
    assert service.engine.get_state("STU001001").last_event == "ENTRY"
    assert service.engine.get_state("STU001001").last_trace_id == "HIAS-20261024-a1b2c3d4-000020"

    # Step 4: High-confidence detection at 17:00 (confidence 0.95 -> AUTO)
    # Must infer EXIT based on confirmed ENTRY, NOT ENTRY (which would happen if rejected events updated state)
    confirmed_exit = {
        "trace_id": "HIAS-20261024-a1b2c3d4-000023",
        "timestamp": "2026-10-24T17:00:00.000Z",
        "student_id": "STU001001",
        "confidence": 0.95,
        "face_detected": True,
    }
    res_exit = service.process(confirmed_exit)
    assert res_exit["status"]["status"] == "AUTO"
    assert res_exit["final_event"]["event"] == "EXIT"
    assert service.engine.get_state("STU001001").last_event == "EXIT"
    assert service.engine.get_state("STU001001").last_trace_id == "HIAS-20261024-a1b2c3d4-000023"


def test_state_recovery_after_restart_continues_working():
    """Verify that existing state recovery after restart restores only confirmed AUTO/CORRECTED events."""
    mock_storage = MagicMock()
    service = IntelligenceService(storage_client=mock_storage)

    persisted_history = [
        {
            "trace_id": "HIAS-20261024-a1b2c3d4-000030",
            "student_id": "STU001001",
            "event": "ENTRY",
            "confidence": 0.95,
            "status": "AUTO",
            "timestamp": "2026-10-24T08:00:00.000Z",
        },
        {
            "trace_id": "HIAS-20261024-a1b2c3d4-000031",
            "student_id": "STU001001",
            "event": "EXIT",
            "confidence": 0.60,
            "status": "REJECT",
            "timestamp": "2026-10-24T10:00:00.000Z",
        },
        {
            "trace_id": "HIAS-20261024-a1b2c3d4-000032",
            "student_id": "STU001001",
            "event": "EXIT",
            "confidence": 0.75,
            "status": "REVIEW",
            "timestamp": "2026-10-24T11:00:00.000Z",
        },
    ]

    mock_storage.fetch_by_student.return_value = {
        "ok": True,
        "status": "OK",
        "events": persisted_history,
    }

    # New incoming event 12:00:00Z with high confidence
    event = {
        "trace_id": "HIAS-20261024-a1b2c3d4-000033",
        "timestamp": "2026-10-24T12:00:00.000Z",
        "student_id": "STU001001",
        "confidence": 0.95,
        "face_detected": True,
    }

    result = service.process(event)
    assert result["ok"] is True
    # Recovered state was ENTRY (from 000030, ignoring REJECT and REVIEW), so new event must be EXIT
    assert result["final_event"]["event"] == "EXIT"
    assert result["status"]["status"] == "AUTO"
    assert service.engine.get_state("STU001001").last_event == "EXIT"
