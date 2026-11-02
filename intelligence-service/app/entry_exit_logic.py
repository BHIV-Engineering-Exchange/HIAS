"""Deterministic ENTRY/EXIT interpretation with duplicate prevention."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union


ANOMALY_ORDER = [
    "DUPLICATE_ENTRY",
    "IMPOSSIBLE_TRANSITION",
    "UNUSUAL_TIME",
    "RAPID_MULTIPLE_ENTRIES",
]


def parse_timestamp(value: str) -> datetime:
    normalized = value
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class StudentState:
    last_event: str
    last_timestamp: datetime
    last_trace_id: str


class EntryExitEngine:
    """Stateful, deterministic attendance inference engine."""

    def __init__(self, duplicate_window_seconds: int = 10, missing_exit_hours: int = 12) -> None:
        self.duplicate_window_seconds = duplicate_window_seconds
        self.missing_exit_seconds = missing_exit_hours * 3600
        self._state: Dict[str, StudentState] = {}

    def get_state(self, student_id: str) -> Optional[StudentState]:
        """Return the current in-memory state for a student."""
        return self._state.get(student_id)

    def clear_state(self, student_id: Optional[str] = None) -> None:
        """Clear state for a specific student or all students."""
        if student_id:
            self._state.pop(student_id, None)
        else:
            self._state.clear()

    def restore_state_from_history(
        self,
        student_id: str,
        events: List[Dict[str, Any]],
    ) -> Optional[StudentState]:
        """
        Restore student state from their latest eligible persisted event.

        Eligible events:
          - Valid dictionary with matching student_id (or unspecified)
          - status in ("AUTO", "CORRECTED") (confirmed attendance)
          - event in ("ENTRY", "EXIT")
          - valid timestamp parseable by parse_timestamp()
          - valid non-empty trace_id

        Deduplication and Ordering:
          - Duplicate trace_ids are deduplicated deterministically (first occurrence kept).
          - Ordered by (timestamp, -original_index, trace_id) descending:
              1. More recent timestamps take precedence.
              2. For equal timestamps, records appended later in storage (lower index)
                 take precedence (e.g. human CORRECTED events).
              3. trace_id breaks any remaining tie deterministically.
        """
        if not events or not isinstance(events, list):
            self._state.pop(student_id, None)
            return None

        seen_trace_ids = set()
        eligible_items = []

        for idx, item in enumerate(events):
            if not isinstance(item, dict):
                continue

            event_student = item.get("student_id")
            if event_student is not None and event_student != student_id:
                continue

            status = item.get("status")
            if status not in ("AUTO", "CORRECTED"):
                continue

            event_type = item.get("event")
            if event_type not in ("ENTRY", "EXIT"):
                continue

            trace_id = item.get("trace_id")
            if not trace_id or not isinstance(trace_id, str):
                continue

            if trace_id in seen_trace_ids:
                continue
            seen_trace_ids.add(trace_id)

            raw_ts = item.get("timestamp")
            if not raw_ts or not isinstance(raw_ts, str):
                continue

            try:
                parsed_ts = parse_timestamp(raw_ts)
            except Exception:
                continue

            eligible_items.append((parsed_ts, -idx, trace_id, event_type))

        if not eligible_items:
            self._state.pop(student_id, None)
            return None

        eligible_items.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        latest = eligible_items[0]

        state = StudentState(
            last_event=latest[3],
            last_timestamp=latest[0],
            last_trace_id=latest[2],
        )
        self._state[student_id] = state
        return state

    def restore_state(self, student_id: str, event: Dict[str, Any]) -> Optional[StudentState]:
        """Restore state directly from a single event dictionary."""
        return self.restore_state_from_history(student_id, [event])

    def commit_state(
        self,
        student_id: str,
        event: Optional[str] = None,
        timestamp: Optional[Union[str, datetime]] = None,
        trace_id: Optional[str] = None,
        *,
        interpretation: Optional[Dict[str, Any]] = None,
    ) -> Optional[StudentState]:
        """
        Explicitly commit and update StudentState for a student.

        Updates in-memory state only when called. Does not modify state for UNKNOWN identities.
        """
        if not student_id or student_id == "UNKNOWN":
            return None

        if interpretation is not None:
            if event is None:
                event = interpretation.get("event")
            if timestamp is None:
                timestamp = interpretation.get("timestamp")
            if trace_id is None:
                trace_id = interpretation.get("trace_id")

        if not event or timestamp is None or not trace_id:
            raise ValueError("student_id, event, timestamp, and trace_id are required to commit state")

        if isinstance(timestamp, str):
            current_ts = parse_timestamp(timestamp)
        elif isinstance(timestamp, datetime):
            current_ts = timestamp if timestamp.tzinfo is not None else timestamp.replace(tzinfo=timezone.utc)
        else:
            raise ValueError(f"Invalid timestamp type: {type(timestamp)}")

        state = StudentState(
            last_event=event,
            last_timestamp=current_ts,
            last_trace_id=trace_id,
        )
        self._state[student_id] = state
        return state

    def interpret(
        self,
        *,
        trace_id: str,
        student_id: str,
        timestamp: str,
        commit: bool = True,
    ) -> Dict[str, Any]:
        """
        Interpret attendance direction and detect anomalies.

        If commit=True (default for backward compatibility with standalone engine tests),
        advances state immediately if not a duplicate.
        When commit=False, performs pure interpretation without mutating state.
        """
        current_ts = parse_timestamp(timestamp)
        previous = self._state.get(student_id)

        requires_review = False
        is_duplicate = False
        anomalies = []
        metadata: Dict[str, Any] = {}

        if previous is None:
            inferred_event = "ENTRY"
        else:
            delta_seconds = (current_ts - previous.last_timestamp).total_seconds()
            metadata["time_since_last"] = max(0.0, float(delta_seconds))

            # Strict alternation rule:
            # ENTRY must be followed by EXIT, EXIT must be followed by ENTRY.
            inferred_event = "EXIT" if previous.last_event == "ENTRY" else "ENTRY"

            if delta_seconds < 0:
                anomalies.append("IMPOSSIBLE_TRANSITION")
                requires_review = True
            elif delta_seconds <= self.duplicate_window_seconds:
                # Ignore rapid repeated detections (real-world camera jitter/noise)
                # and do not advance state for these events.
                anomalies.append("RAPID_MULTIPLE_ENTRIES")
                if previous.last_event == "ENTRY":
                    anomalies.append("DUPLICATE_ENTRY")
                requires_review = True
                is_duplicate = True
                metadata["ignored_duplicate"] = True
                metadata["ignore_reason"] = "rapid_repeat_within_window"
                metadata["duplicate_window_seconds"] = self.duplicate_window_seconds
            elif previous.last_event == "ENTRY" and delta_seconds >= self.missing_exit_seconds:
                # Long-running open entry without timely counterpart.
                anomalies.append("IMPOSSIBLE_TRANSITION")
                requires_review = True

            if previous.last_event == "ENTRY":
                metadata["last_entry"] = previous.last_timestamp.isoformat().replace("+00:00", "Z")

        if current_ts.hour < 5:
            anomalies.append("UNUSUAL_TIME")
            requires_review = True

        unique_anomalies = [name for name in ANOMALY_ORDER if name in set(anomalies)]

        if commit and not is_duplicate and student_id != "UNKNOWN":
            self.commit_state(
                student_id=student_id,
                event=inferred_event,
                timestamp=current_ts,
                trace_id=trace_id,
            )

        return {
            "event": inferred_event,
            "anomaly_flags": unique_anomalies,
            "requires_review": requires_review,
            "is_duplicate": is_duplicate,
            "metadata": metadata,
            "trace_id": trace_id,
            "timestamp": current_ts,
            "student_id": student_id,
        }
