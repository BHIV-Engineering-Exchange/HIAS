import os
from app.validator import SchemaValidator

def test_schema_dir_and_load():
    """Validator should locate the schema directory and load required schemas."""
    # Ensure environment does not interfere
    validator = SchemaValidator()
    # The schema directory should exist
    assert validator.schema_dir.is_dir(), f"Schema dir not found: {validator.schema_dir}"
    # Expected schema files must be loaded
    for name in [
        "storage.schema.json",
        "ingestion.schema.json",
        "recognition.schema.json",
        "intelligence.schema.json",
        "confidence.schema.json",
        "human-loop.schema.json",
        "observability.schema.json",
        "error.schema.json",
    ]:
        assert name in validator.schemas, f"{name} not loaded"
