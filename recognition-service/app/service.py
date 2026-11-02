"""Recognition service core logic."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.errors import build_error
from app.face_detection import DeterministicFaceDetector
from app.schema_registry import SchemaRegistry
from app.student_matcher import DeterministicStudentMatcher


class RecognitionService:
    """Deterministic recognition with strict contract validation."""

    def __init__(
        self,
        *,
        schema_registry: Optional[SchemaRegistry] = None,
        detector: Optional[DeterministicFaceDetector] = None,
        matcher: Optional[DeterministicStudentMatcher] = None,
    ) -> None:
        self.schemas = schema_registry or SchemaRegistry()
        self.detector = detector or DeterministicFaceDetector()
        self.matcher = matcher or DeterministicStudentMatcher()

    def _reject(
        self,
        *,
        code: str,
        message: str,
        trace_id: Optional[str] = None,
        error_type: str = "SCHEMA_VALIDATION",
        severity: str = "MEDIUM",
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

    def process(self, ingestion_event: Dict[str, Any]) -> Dict[str, Any]:
        trace_id: Optional[str] = None
        try:
            if not isinstance(ingestion_event, dict):
                return self._reject(
                    code="ERR_INVALID_PAYLOAD",
                    message="Payload must be a JSON object",
                    error_type="OTHER",
                    severity="HIGH",
                )

            trace_id = ingestion_event.get("trace_id")
            input_valid, input_error = self.schemas.validate("ingestion.schema.json", ingestion_event)
            if not input_valid:
                return self._reject(
                    code="ERR_INVALID_INPUT_SCHEMA",
                    message=input_error or "Invalid ingestion schema payload",
                    trace_id=trace_id,
                    context={"schema": "ingestion.schema.json"},
                )

            detection = self.detector.detect(ingestion_event)
            matching = self.matcher.match(
                trace_id=ingestion_event["trace_id"],
                signature=detection["signature"],
                face_detected=detection["face_detected"],
                image_size=int(ingestion_event["image_data"]["size"]),
            )

            face_detected = bool(detection.get("face_detected", False))
            student_id = matching.get("student_id")
            confidence = float(matching.get("confidence", 0.0))

            # Hard guard: if no face detected, identity must be null and confidence must be zero.
            if not face_detected:
                student_id = None
                confidence = 0.0

            # Keep confidence strictly within contract bounds.
            confidence = max(0.0, min(1.0, round(confidence, 2)))

            recognition_event: Dict[str, Any] = {
                "trace_id": ingestion_event["trace_id"],
                "timestamp": ingestion_event["timestamp"],
                "student_id": student_id,
                "confidence": confidence,
                "face_detected": face_detected,
            }
            face_bbox = detection.get("face_bbox")
            if face_bbox is not None:
                recognition_event["face_bbox"] = face_bbox
            similar_candidates = matching.get("similar_candidates") or []
            if similar_candidates:
                recognition_event["similar_candidates"] = similar_candidates

            output_valid, output_error = self.schemas.validate("recognition.schema.json", recognition_event)
            if not output_valid:
                return self._reject(
                    code="ERR_INVALID_OUTPUT_SCHEMA",
                    message=output_error or "Invalid recognition output",
                    trace_id=trace_id,
                    context={"schema": "recognition.schema.json"},
                )

            return {"ok": True, "event": recognition_event}
        except Exception as exc:  # pragma: no cover - defensive safety net
            return self._reject(
                code="ERR_RECOGNITION_PROCESSING",
                message=str(exc),
                trace_id=trace_id,
                error_type="OTHER",
                severity="HIGH",
            )
