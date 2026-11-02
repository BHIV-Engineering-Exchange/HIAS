"""
Reference: Validate a payload against storage.schema.json before sending.

Services MUST validate locally before calling /store-event to avoid
unnecessary rejected writes.
"""

import json
from pathlib import Path
from jsonschema import validate, ValidationError

_SCHEMA_PATH = Path(__file__).parent.parent.parent / "shared-contracts" / "schemas" / "storage.schema.json"

with open(_SCHEMA_PATH) as f:
    _STORAGE_SCHEMA = json.load(f)


def validate_storage_payload(payload: dict) -> tuple[bool, str | None]:
    """
    Returns (True, None) if valid.
    Returns (False, error_message) if invalid.
    """
    try:
        validate(instance=payload, schema=_STORAGE_SCHEMA)
        return True, None
    except ValidationError as e:
        return False, e.message


# ── Example usage ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    good = {
        "trace_id": "HIAS-20260429-abcdef12-000001",
        "timestamp": "2026-04-29T13:15:00Z",
        "student_id": "STU123456",
        "event": "ENTRY",
        "confidence": 0.92,
        "status": "AUTO",
        "source_service": "confidence_service",
    }
    print(validate_storage_payload(good))   # (True, None)

    bad = {"trace_id": "HIAS-20260429-abcdef12-000001"}
    print(validate_storage_payload(bad))    # (False, "... is a required property")
