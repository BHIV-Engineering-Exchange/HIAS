"""
Test: Append-Only Enforcement
Verifies new events are accepted and mutations/duplicates are rejected.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from app.writer import StorageWriter


VALID_EVENT = {
    "trace_id": "HIAS-20260418-a1b2c3d4-000001",
    "timestamp": "2026-04-18T08:00:00Z",
    "student_id": "STU001001",
    "event": "ENTRY",
    "confidence": 0.95,
    "status": "AUTO",
    "source_service": "confidence_service",
    "camera_id": "GATE-MAIN",
    "zone": "GATE_MAIN",
}


def _make_writer():
    """Return a StorageWriter with MongoDB calls mocked out."""
    with patch("app.writer.events_collection") as mock_events, \
         patch("app.writer.chain_state_collection") as mock_chain, \
         patch("app.writer.client") as mock_client:

        mock_events.find_one.return_value = None  # no existing record
        mock_chain.find_one.return_value = None    # no chain state yet

        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        mock_client.start_session.return_value = session

        from app.writer import StorageWriter
        writer = StorageWriter()
        writer._mock_events = mock_events
        writer._mock_chain = mock_chain
        writer._mock_client = mock_client
        writer._mock_session = session
        return writer, mock_events, mock_chain, mock_client


def test_append_new_event():
    """New events should be accepted."""
    with patch("app.writer.events_collection") as mock_events, \
         patch("app.writer.chain_state_collection") as mock_chain, \
         patch("app.writer.client") as mock_client:

        mock_events.find_one.return_value = None
        mock_chain.find_one.return_value = None
        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        mock_client.start_session.return_value = session

        from app.writer import StorageWriter
        writer = StorageWriter()
        result = writer.append_event(VALID_EVENT)

    assert result["success"] is True
    assert result["trace_id"] == VALID_EVENT["trace_id"]
    assert result["event_id"] is not None
    assert len(result["hash"]) == 64


def test_reject_duplicate_trace_id():
    """Duplicate trace_id must be rejected (append-only)."""
    with patch("app.writer.events_collection") as mock_events, \
         patch("app.writer.chain_state_collection") as mock_chain, \
         patch("app.writer.client") as mock_client:

        # Simulate existing record
        mock_events.find_one.return_value = {"trace_id": VALID_EVENT["trace_id"]}
        mock_chain.find_one.return_value = None
        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        mock_client.start_session.return_value = session

        from app.writer import StorageWriter
        writer = StorageWriter()
        result = writer.append_event(VALID_EVENT)

    assert result["success"] is False
    assert "already exists" in result["error"].lower()


def test_reject_malformed_event():
    """Events missing required fields must be rejected."""
    with patch("app.writer.events_collection"), \
         patch("app.writer.chain_state_collection"), \
         patch("app.writer.client"):

        from app.writer import StorageWriter
        writer = StorageWriter()
        result = writer.append_event({
            "trace_id": "HIAS-20260418-a1b2c3d4-000002",
            "timestamp": "2026-04-18T08:00:00Z",
        })

    assert result["success"] is False
    assert "validation" in result["error"].lower()


def test_sequence_of_events():
    """Multiple unique events should all be accepted with unique hashes."""
    results = []

    for i in range(1, 4):
        event = {**VALID_EVENT,
                 "trace_id": f"HIAS-20260418-a1b2c3d4-00000{i}",
                 "student_id": f"STU00{i}00{i}"}

        with patch("app.writer.events_collection") as mock_events, \
             patch("app.writer.chain_state_collection") as mock_chain, \
             patch("app.writer.client") as mock_client:

            mock_events.find_one.return_value = None
            mock_chain.find_one.return_value = None
            session = MagicMock()
            session.__enter__ = MagicMock(return_value=session)
            session.__exit__ = MagicMock(return_value=False)
            mock_client.start_session.return_value = session

            from app.writer import StorageWriter
            writer = StorageWriter()
            result = writer.append_event(event)
            assert result["success"] is True
            results.append(result)

    hashes = [r["hash"] for r in results]
    assert len(set(hashes)) == len(hashes), "Each event must have a unique hash"


def test_format_timestamp_without_fractional_seconds():
    """Verify timestamps without fractional seconds preserve existing behavior."""
    writer = StorageWriter()

    # None input
    assert writer._format_timestamp_for_hash(None) is None

    # String without fractional seconds
    assert writer._format_timestamp_for_hash("2026-04-18T08:00:00Z") == "2026-04-18T08:00:00Z"

    # String with +00:00 offset
    assert writer._format_timestamp_for_hash("2026-04-18T08:00:00+00:00") == "2026-04-18T08:00:00Z"

    # Aware UTC datetime without fractional seconds
    dt_utc = datetime(2026, 4, 18, 8, 0, 0, tzinfo=timezone.utc)
    assert writer._format_timestamp_for_hash(dt_utc) == "2026-04-18T08:00:00Z"

    # Naive datetime without fractional seconds
    dt_naive = datetime(2026, 4, 18, 8, 0, 0)
    assert writer._format_timestamp_for_hash(dt_naive) == "2026-04-18T08:00:00Z"


def test_format_timestamp_with_fractional_seconds():
    """Verify timestamps with fractional seconds are normalized to UTC preserving precision."""
    writer = StorageWriter()

    # String with millisecond precision (.123Z)
    assert writer._format_timestamp_for_hash("2026-10-24T08:15:30.123Z") == "2026-10-24T08:15:30.123Z"

    # String with offset normalized to UTC preserving fractional seconds
    assert writer._format_timestamp_for_hash("2026-10-24T13:45:30.123+05:30") == "2026-10-24T08:15:30.123Z"

    # Aware UTC datetime with millisecond precision
    dt_utc = datetime(2026, 10, 24, 8, 15, 30, 123000, tzinfo=timezone.utc)
    assert writer._format_timestamp_for_hash(dt_utc) == "2026-10-24T08:15:30.123Z"

    # Aware non-UTC datetime normalized to UTC with fractional seconds
    dt_offset = datetime(2026, 10, 24, 13, 45, 30, 123000, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert writer._format_timestamp_for_hash(dt_offset) == "2026-10-24T08:15:30.123Z"

    # Microsecond precision
    dt_micro = datetime(2026, 10, 24, 8, 15, 30, 123456, tzinfo=timezone.utc)
    assert writer._format_timestamp_for_hash(dt_micro) == "2026-10-24T08:15:30.123456Z"


def test_reconstructed_hash_matches_original_without_fractional_seconds():
    """Verify reconstructed hash matches original hash for timestamps without fractional seconds."""
    writer = StorageWriter()
    prev_hash = writer.hash_chain.GENESIS_HASH

    event = {
        **VALID_EVENT,
        "trace_id": "HIAS-20260418-a1b2c3d4-000010",
        "timestamp": "2026-04-18T08:00:00Z",
    }

    event_for_hash = {k: v for k, v in event.items() if k not in {"hash", "prev_hash", "created_at", "event_id"}}
    event_for_hash["timestamp"] = writer._format_timestamp_for_hash(event_for_hash["timestamp"])
    original_hash = writer.hash_chain.generate_hash(prev_hash, event_for_hash)

    # Convert to stored representation (datetime in MongoDB)
    stored_timestamp = writer._parse_timestamp(event["timestamp"])
    assert isinstance(stored_timestamp, datetime)
    assert stored_timestamp.microsecond == 0

    # Reconstruct timestamp from stored representation
    reconstructed_timestamp = writer._format_timestamp_for_hash(stored_timestamp)
    assert reconstructed_timestamp == event["timestamp"]

    # Reconstruct event and verify hash matches
    reconstructed_event = {**event_for_hash, "timestamp": reconstructed_timestamp}
    reconstructed_hash = writer.hash_chain.generate_hash(prev_hash, reconstructed_event)
    assert reconstructed_hash == original_hash


def test_reconstructed_hash_matches_original_with_fractional_seconds():
    """Verify reconstructed hash matches original hash for timestamps with fractional seconds (e.g. 2026-10-24T08:15:30.123Z)."""
    writer = StorageWriter()
    prev_hash = writer.hash_chain.GENESIS_HASH

    event = {
        **VALID_EVENT,
        "trace_id": "HIAS-20261024-a1b2c3d4-000020",
        "timestamp": "2026-10-24T08:15:30.123Z",
    }

    event_for_hash = {k: v for k, v in event.items() if k not in {"hash", "prev_hash", "created_at", "event_id"}}
    event_for_hash["timestamp"] = writer._format_timestamp_for_hash(event_for_hash["timestamp"])
    original_hash = writer.hash_chain.generate_hash(prev_hash, event_for_hash)

    # Convert to stored representation (datetime in MongoDB)
    stored_timestamp = writer._parse_timestamp(event["timestamp"])
    assert isinstance(stored_timestamp, datetime)
    assert stored_timestamp.microsecond == 123000

    # Reconstruct timestamp from stored representation
    reconstructed_timestamp = writer._format_timestamp_for_hash(stored_timestamp)
    assert reconstructed_timestamp == "2026-10-24T08:15:30.123Z"

    # Reconstruct event and verify hash matches
    reconstructed_event = {**event_for_hash, "timestamp": reconstructed_timestamp}
    reconstructed_hash = writer.hash_chain.generate_hash(prev_hash, reconstructed_event)
    assert reconstructed_hash == original_hash


def test_append_event_and_verify_chain_integrity_with_fractional_seconds():
    """Verify that an appended event with fractional seconds verifies cleanly via verify_chain_integrity()."""
    with patch("app.writer.events_collection") as mock_events, \
         patch("app.writer.chain_state_collection") as mock_chain, \
         patch("app.writer.client") as mock_client:

        mock_events.find_one.return_value = None
        mock_chain.find_one.return_value = None
        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        mock_client.start_session.return_value = session

        writer = StorageWriter()
        event = {
            **VALID_EVENT,
            "trace_id": "HIAS-20261024-a1b2c3d4-000030",
            "timestamp": "2026-10-24T08:15:30.123Z",
        }

        result = writer.append_event(event)
        assert result["success"] is True

        # Check stored document has datetime with fractional seconds
        stored_doc = mock_events.insert_one.call_args[0][0]
        assert isinstance(stored_doc["timestamp"], datetime)
        assert stored_doc["timestamp"].microsecond == 123000

        # Mock collection find returning the stored document
        mock_events.find.return_value.sort.return_value = [stored_doc]

        integrity = writer.verify_chain_integrity()
        assert integrity["valid"] is True
        assert integrity["error"] is None
        assert integrity["total_events"] == 1


def test_chain_integrity_mixed_timestamps_sequence():
    """Verify chain integrity across events with and without fractional seconds."""
    with patch("app.writer.events_collection") as mock_events, \
         patch("app.writer.chain_state_collection") as mock_chain, \
         patch("app.writer.client") as mock_client:

        mock_events.find_one.return_value = None
        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        mock_client.start_session.return_value = session

        writer = StorageWriter()

        events_to_append = [
            {
                **VALID_EVENT,
                "trace_id": "HIAS-20261024-a1b2c3d4-000041",
                "timestamp": "2026-04-18T08:00:00Z",
            },
            {
                **VALID_EVENT,
                "trace_id": "HIAS-20261024-a1b2c3d4-000042",
                "timestamp": "2026-10-24T08:15:30.123Z",
            },
            {
                **VALID_EVENT,
                "trace_id": "HIAS-20261024-a1b2c3d4-000043",
                "timestamp": "2026-10-24T08:15:45.500Z",
            },
        ]

        stored_docs = []
        current_last_hash = writer.hash_chain.GENESIS_HASH

        for ev in events_to_append:
            mock_chain.find_one.return_value = {"_id": "global", "last_hash": current_last_hash}
            res = writer.append_event(ev)
            assert res["success"] is True
            current_last_hash = res["hash"]
            doc = mock_events.insert_one.call_args[0][0]
            stored_docs.append(doc)

        mock_events.find.return_value.sort.return_value = stored_docs
        integrity = writer.verify_chain_integrity()
        assert integrity["valid"] is True
        assert integrity["error"] is None
        assert integrity["total_events"] == 3


def test_append_event_preserves_original_event_unmutated():
    """Verify append_event does not mutate caller's event dictionary or timestamp."""
    with patch("app.writer.events_collection") as mock_events, \
         patch("app.writer.chain_state_collection") as mock_chain, \
         patch("app.writer.client") as mock_client:

        mock_events.find_one.return_value = None
        mock_chain.find_one.return_value = None
        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        mock_client.start_session.return_value = session

        writer = StorageWriter()

        original_timestamp = "2026-10-24T08:15:30.123Z"
        event = {
            **VALID_EVENT,
            "trace_id": "HIAS-20261024-a1b2c3d4-000050",
            "timestamp": original_timestamp,
        }
        event_copy = dict(event)

        result = writer.append_event(event)
        assert result["success"] is True
        assert event["timestamp"] == original_timestamp
        assert event == event_copy


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
