"""Ingestion service core logic."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.errors import build_error
from app.schema_registry import SchemaRegistry
from app.trace_generator import TraceGenerator


class IngestionService:
    """Deterministic ingestion boundary with strict contract validation."""

    _ALLOWED_FIELDS = {"trace_id", "timestamp", "camera_id", "zone", "image_data", "sequence_num"}

    def __init__(
        self,
        *,
        schema_registry: Optional[SchemaRegistry] = None,
        trace_generator: Optional[TraceGenerator] = None,
    ) -> None:
        self.schemas = schema_registry or SchemaRegistry()
        self.trace_generator = trace_generator or TraceGenerator()

    def _reject(
        self,
        *,
        code: str,
        message: str,
        error_type: str = "SCHEMA_VALIDATION",
        severity: str = "MEDIUM",
        trace_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": build_error(
                error_code=code,
                severity=severity,
                error_type=error_type,
                error_message=message,
                trace_id=trace_id,
                context=context,
            ),
        }

    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize camera input into ingestion contract output."""
        try:
            if not isinstance(payload, dict):
                return self._reject(
                    code="ERR_INVALID_PAYLOAD",
                    message="Payload must be a JSON object",
                    error_type="OTHER",
                    severity="HIGH",
                )

            cleaned = {key: payload[key] for key in self._ALLOWED_FIELDS if key in payload}
            trace_id = cleaned.get("trace_id")

            for field_name in ("timestamp", "camera_id", "image_data"):
                if field_name not in cleaned:
                    return self._reject(
                        code="ERR_INVALID_PAYLOAD",
                        message=f"Missing required field: {field_name}",
                        trace_id=trace_id,
                        context={"field": field_name},
                    )
                if cleaned[field_name] is None:
                    return self._reject(
                        code="ERR_INVALID_PAYLOAD",
                        message=f"Null value is not allowed for field: {field_name}",
                        trace_id=trace_id,
                        context={"field": field_name},
                    )

            image_data = cleaned.get("image_data")
            if not isinstance(image_data, dict):
                return self._reject(
                    code="ERR_MISSING_IMAGE",
                    message="image_data must be an object",
                    trace_id=trace_id,
                    context={"image_data_type": str(type(image_data))},
                )

            if image_data.get("size") is None or image_data.get("format") is None:
                return self._reject(
                    code="ERR_MISSING_IMAGE",
                    message="image_data.format and image_data.size are required",
                    trace_id=trace_id,
                )

            if "trace_id" not in cleaned or not cleaned["trace_id"]:
                cleaned["trace_id"] = self.trace_generator.generate(
                    timestamp=cleaned["timestamp"],
                    camera_id=cleaned["camera_id"],
                    image_data=image_data,
                    sequence_num=cleaned.get("sequence_num"),
                )

            validation_result = self.schemas.validate(
                schema_name="ingestion.schema.json",
                payload=cleaned,
            )
            valid, error_msg = validation_result
            if not valid:
                return self._reject(
                    code="ERR_INVALID_PAYLOAD",
                    message=error_msg or "Schema validation failed",
                    trace_id=cleaned.get("trace_id"),
                )

            return {
                "ok": True,
                "event": {
                    "trace_id": cleaned["trace_id"],
                    "timestamp": cleaned["timestamp"],
                    "camera_id": cleaned["camera_id"],
                    "zone": cleaned.get("zone"),
                    "image_data": image_data,
                    **({"sequence_num": cleaned["sequence_num"]} if "sequence_num" in cleaned else {}),
                },
            }

        except Exception as e:
            return self._reject(
                code="ERR_EXCEPTION",
                message=str(e),
                error_type="INTERNAL",
                severity="HIGH",
                trace_id=trace_id if "trace_id" in locals() else None,
            )
