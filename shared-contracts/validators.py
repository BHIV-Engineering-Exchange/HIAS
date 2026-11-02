"""
Shared contract validators — import from here, not from individual services.
"""

import json
from pathlib import Path
from jsonschema import validate, ValidationError

_SCHEMA_DIR = Path(__file__).parent / "schemas"
_SCHEMAS: dict = {}


def _load(name: str) -> dict:
    if name not in _SCHEMAS:
        with open(_SCHEMA_DIR / name) as f:
            _SCHEMAS[name] = json.load(f)
    return _SCHEMAS[name]


def validate_event(schema_name: str, payload: dict) -> tuple[bool, str | None]:
    """Validate payload against named schema. Returns (valid, error_or_None)."""
    try:
        validate(instance=payload, schema=_load(schema_name))
        return True, None
    except ValidationError as e:
        return False, e.message


# Convenience wrappers
def validate_storage(p: dict):   return validate_event("storage.schema.json", p)
def validate_ingestion(p: dict): return validate_event("ingestion.schema.json", p)
def validate_recognition(p: dict): return validate_event("recognition.schema.json", p)
def validate_intelligence(p: dict): return validate_event("intelligence.schema.json", p)
def validate_confidence(p: dict): return validate_event("confidence.schema.json", p)
def validate_human_loop(p: dict): return validate_event("human-loop.schema.json", p)
def validate_observability(p: dict): return validate_event("observability.schema.json", p)
def validate_error(p: dict):     return validate_event("error.schema.json", p)
