"""
Camera Intelligence Integration Adapter — Audit-Only Mode

Receives final events from the Camera Intelligence service and persists them
as REVIEW events for human audit.  No physical gate access is granted.

Configuration:
    CAMERA_INTELLIGENCE_ENABLED  — Set to "true" to accept camera events (default: false)
    CAMERA_STUDENT_MAP           — Mapping string in 'student_id:user_id' comma-separated format
"""

import os
import re
import logging
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple

from pydantic import BaseModel, Field, field_validator, ConfigDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Contract regular expressions (aligned with storage.schema.json)
# ---------------------------------------------------------------------------

TRACE_ID_REGEX = re.compile(r"^HIAS-[0-9]{8}-[a-f0-9]{8}-[0-9]{6}$")
STUDENT_ID_REGEX = re.compile(r"^[A-Z0-9]{6,10}$")

# ---------------------------------------------------------------------------
# Configuration & Mapping
# ---------------------------------------------------------------------------

CAMERA_INTELLIGENCE_ENABLED: bool = (
    os.getenv("CAMERA_INTELLIGENCE_ENABLED", "false").lower() == "true"
)


def parse_student_user_mapping(raw: str) -> dict[str, str]:
    """
    Parse a comma-separated 'student_id:user_id' mapping string.

    Rules:
      - Empty or whitespace-only input returns an empty dictionary.
      - Reject malformed entries (missing colon, extra colons).
      - Reject empty student_id or user_id.
      - Reject duplicate source student_id keys.
      - Never infer default identity mappings.
    """
    mapping: dict[str, str] = {}
    if not raw or not raw.strip():
        return mapping

    entries = raw.split(",")
    for entry in entries:
        trimmed = entry.strip()
        if not trimmed:
            raise ValueError(f"Malformed mapping: empty entry in '{raw}'")
        parts = trimmed.split(":")
        if len(parts) != 2:
            raise ValueError(
                f"Malformed mapping entry '{trimmed}': expected 'student_id:user_id'"
            )
        student_id, user_id = parts[0].strip(), parts[1].strip()
        if not student_id or not user_id:
            raise ValueError(
                f"Malformed mapping entry '{trimmed}': student_id and user_id cannot be empty"
            )
        if student_id in mapping:
            raise ValueError(
                f"Duplicate source student_id '{student_id}' in mapping configuration"
            )
        mapping[student_id] = user_id

    return mapping


def load_student_user_mapping() -> dict[str, str]:
    """Load student mappings exclusively from the CAMERA_STUDENT_MAP environment variable."""
    return parse_student_user_mapping(os.getenv("CAMERA_STUDENT_MAP", ""))


# Empty by default; only populated via CAMERA_STUDENT_MAP
STUDENT_USER_MAPPING: dict[str, str] = load_student_user_mapping()


# ---------------------------------------------------------------------------
# Contract Enums & Models
# ---------------------------------------------------------------------------

class CameraEventType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class CameraEventStatus(str, Enum):
    AUTO = "AUTO"
    REVIEW = "REVIEW"
    REJECT = "REJECT"
    CORRECTED = "CORRECTED"


class CameraSourceService(str, Enum):
    CONFIDENCE_SERVICE = "confidence_service"
    HUMAN_LOOP_SERVICE = "human_loop_service"


class CameraIntelligenceEvent(BaseModel):
    """
    Pydantic model validating final camera events against storage.schema.json.
    Rejects any unrecognized fields.
    """

    model_config = ConfigDict(extra="forbid")

    trace_id: str
    timestamp: str
    student_id: str
    event: CameraEventType
    confidence: float = Field(ge=0.0, le=1.0)
    status: CameraEventStatus
    source_service: CameraSourceService

    @field_validator("trace_id")
    @classmethod
    def validate_trace_id_format(cls, v: str) -> str:
        if not isinstance(v, str) or not TRACE_ID_REGEX.match(v):
            raise ValueError(
                f"trace_id must match format '^HIAS-[0-9]{{8}}-[a-f0-9]{{8}}-[0-9]{{6}}$', got '{v}'"
            )
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp_format(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            raise ValueError(f"Invalid ISO-8601 timestamp: '{v}'")
        return v

    @field_validator("student_id")
    @classmethod
    def validate_student_id_format(cls, v: str) -> str:
        if not isinstance(v, str) or not STUDENT_ID_REGEX.match(v):
            raise ValueError(
                f"student_id must match format '^[A-Z0-9]{{6,10}}$', got '{v}'"
            )
        if v.upper() == "UNKNOWN":
            raise ValueError("student_id 'UNKNOWN' is not accepted")
        return v


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------

def validate_and_map_event(
    event: CameraIntelligenceEvent,
    mapping: Optional[dict[str, str]] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate that a camera event can be mapped to an existing HIAS user.

    Returns:
        (is_valid, hias_user_id | None, error_message | None)
    """
    active_mapping = mapping if mapping is not None else STUDENT_USER_MAPPING
    hias_user_id = active_mapping.get(event.student_id)
    if not hias_user_id:
        return (
            False,
            None,
            f"No HIAS user mapping for student_id '{event.student_id}'",
        )
    return True, hias_user_id, None
