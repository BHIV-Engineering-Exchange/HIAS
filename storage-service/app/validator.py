"""
Schema Validator — Ensures all events match shared-contracts

Rules:
✅ Every event MUST match storage.schema.json before storage
✅ Reject any contract violations
✅ Emit error signals for validation failures
"""

import json
import logging
from jsonschema import validate, ValidationError
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class SchemaValidator:
    """Validates events against shared-contracts"""

    def __init__(self, schema_dir: str = None):
        """
        Initialize validator with schema directory

        Args:
            schema_dir: Path to shared-contracts/schemas directory
        """
        if schema_dir is None:
            # Default path relative to storage-service
            # Determine schema directory for both local development and Docker
            dev_path = Path(__file__).parent.parent.parent / "shared-contracts" / "schemas"
            docker_path = Path(__file__).parent.parent / "shared-contracts" / "schemas"
            schema_dir = dev_path if dev_path.is_dir() else docker_path

        self.schema_dir = Path(schema_dir)
        self.schemas = {}
        self._load_schemas()

    def _load_schemas(self):
        """Load all schema files into memory"""
        required_schemas = [
            'storage.schema.json',
            'ingestion.schema.json',
            'recognition.schema.json',
            'intelligence.schema.json',
            'confidence.schema.json',
            'human-loop.schema.json',
            'observability.schema.json',
            'error.schema.json'
        ]

        for schema_name in required_schemas:
            schema_path = self.schema_dir / schema_name
            try:
                with open(schema_path, 'r') as f:
                    self.schemas[schema_name] = json.load(f)
                logger.info(f"✅ Loaded schema: {schema_name}")
            except FileNotFoundError:
                logger.warning(f"⚠️  Schema not found: {schema_path}")
            except json.JSONDecodeError as e:
                logger.error(f"❌ Invalid JSON in {schema_name}: {str(e)}")

    def validate_storage_event(self, event: dict) -> Tuple[bool, Optional[str]]:
        """
        Validate event against storage.schema.json

        This is the CRITICAL validation point — all events must pass here
        before being stored.

        Args:
            event: Event data to validate

        Returns:
            (is_valid: bool, error_message: Optional[str])
        """
        if 'storage.schema.json' not in self.schemas:
            return False, "Storage schema not loaded"

        try:
            validate(instance=event, schema=self.schemas['storage.schema.json'])
            return True, None
        except ValidationError as e:
            error_msg = f"Schema validation failed: {e.message} at path '{'.'.join(str(p) for p in e.path)}'"
            logger.warning(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Validation error: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def validate_ingestion_event(self, event: dict) -> Tuple[bool, Optional[str]]:
        """Validate against ingestion.schema.json"""
        if 'ingestion.schema.json' not in self.schemas:
            return False, "Ingestion schema not loaded"

        try:
            validate(instance=event, schema=self.schemas['ingestion.schema.json'])
            return True, None
        except ValidationError as e:
            return False, f"Ingestion validation failed: {e.message}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def validate_recognition_event(self, event: dict) -> Tuple[bool, Optional[str]]:
        """Validate against recognition.schema.json"""
        if 'recognition.schema.json' not in self.schemas:
            return False, "Recognition schema not loaded"

        try:
            validate(instance=event, schema=self.schemas['recognition.schema.json'])
            return True, None
        except ValidationError as e:
            return False, f"Recognition validation failed: {e.message}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def validate_intelligence_event(self, event: dict) -> Tuple[bool, Optional[str]]:
        """Validate against intelligence.schema.json"""
        if 'intelligence.schema.json' not in self.schemas:
            return False, "Intelligence schema not loaded"

        try:
            validate(instance=event, schema=self.schemas['intelligence.schema.json'])
            return True, None
        except ValidationError as e:
            return False, f"Intelligence validation failed: {e.message}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def validate_confidence_event(self, event: dict) -> Tuple[bool, Optional[str]]:
        """Validate against confidence.schema.json"""
        if 'confidence.schema.json' not in self.schemas:
            return False, "Confidence schema not loaded"

        try:
            validate(instance=event, schema=self.schemas['confidence.schema.json'])
            return True, None
        except ValidationError as e:
            return False, f"Confidence validation failed: {e.message}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def validate_human_loop_event(self, event: dict) -> Tuple[bool, Optional[str]]:
        """Validate against human-loop.schema.json"""
        if 'human-loop.schema.json' not in self.schemas:
            return False, "Human loop schema not loaded"

        try:
            validate(instance=event, schema=self.schemas['human-loop.schema.json'])
            return True, None
        except ValidationError as e:
            return False, f"Human loop validation failed: {e.message}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def validate_trace_id(self, trace_id: str) -> Tuple[bool, Optional[str]]:
        """
        Validate trace_id format

        Format: HIAS-YYYYMMDD-XXXXXXXX-XXXXXX
        Example: HIAS-20260418-a1b2c3d4-000001
        """
        import re

        pattern = r'^HIAS-[0-9]{8}-[a-f0-9]{8}-[0-9]{6}$'
        if re.match(pattern, trace_id):
            return True, None
        else:
            return False, f"Invalid trace_id format: {trace_id}"

    def validate_required_fields(self, event: dict, required_fields: list) -> Tuple[bool, Optional[str]]:
        """Validate that all required fields are present"""
        missing = [field for field in required_fields if field not in event]
        if missing:
            return False, f"Missing required fields: {', '.join(missing)}"
        return True, None

    def validate_no_mutation(self, existing_event: dict, incoming_event: dict) -> Tuple[bool, Optional[str]]:
        """
        Validate that incoming event is NOT a mutation attempt

        Since storage is append-only, we should NEVER see an update to an existing record.
        """
        # This is a placeholder for mutation detection
        # In practice, we check if a record with same ID exists and incoming data differs
        if existing_event.get('event_id') == incoming_event.get('event_id'):
            return False, "Mutation attempt detected: Cannot update existing records (append-only constraint)"
        return True, None


# ============================================================================
# VALIDATION EXAMPLES (For Testing)
# ============================================================================

def demo_validation():
    """Demonstration of schema validation"""
    validator = SchemaValidator()

    # Valid event
    valid_event = {
        "trace_id": "HIAS-20260418-a1b2c3d4-000001",
        "timestamp": "2026-04-18T08:00:00Z",
        "student_id": "STU001",
        "event": "ENTRY",
        "confidence": 0.95,
        "status": "AUTO",
        "source_service": "confidence_service",
        "camera_id": "GATE-MAIN",
        "zone": "GATE_MAIN"
    }

    is_valid, error = validator.validate_storage_event(valid_event)
    print(f"Valid Event: {is_valid}")
    if error:
        print(f"  Error: {error}")

    # Invalid event (missing required field)
    invalid_event = {
        "trace_id": "HIAS-20260418-a1b2c3d4-000001",
        "timestamp": "2026-04-18T08:00:00Z",
        # Missing: student_id, event, confidence, status, source_service
    }

    is_valid, error = validator.validate_storage_event(invalid_event)
    print(f"\nInvalid Event: {is_valid}")
    if error:
        print(f"  Error: {error}")

    # Trace ID validation
    is_valid, error = validator.validate_trace_id("HIAS-20260418-a1b2c3d4-000001")
    print(f"\nValid Trace ID: {is_valid}")

    is_valid, error = validator.validate_trace_id("INVALID-TRACE-ID")
    print(f"Invalid Trace ID: {is_valid}")
    print(f"  Error: {error}")


if __name__ == "__main__":
    demo_validation()
