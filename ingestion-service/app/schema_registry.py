"""Schema loading and strict validation utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from jsonschema import Draft7Validator, FormatChecker


class SchemaRegistry:
    """Loads and validates shared schema contracts."""

    def __init__(self, schema_dir: Optional[Path] = None) -> None:
        if schema_dir is None:
            schema_dir = Path(__file__).resolve().parents[2] / "shared-contracts" / "schemas"
        self.schema_dir = Path(schema_dir)
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _load_schema(self, schema_name: str) -> Dict[str, Any]:
        if schema_name not in self._cache:
            path = self.schema_dir / schema_name
            with path.open("r", encoding="utf-8") as handle:
                self._cache[schema_name] = json.load(handle)
        return self._cache[schema_name]

    def validate(self, schema_name: str, payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        schema = self._load_schema(schema_name)
        validator = Draft7Validator(schema=schema, format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
        if not errors:
            return True, None

        first = errors[0]
        path = ".".join(str(part) for part in first.path) or "$"
        return False, f"{first.message} at {path}"
