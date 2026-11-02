"""Intelligence service core logic."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.confidence_router import ConfidenceRouter
from app.entry_exit_logic import EntryExitEngine
from app.errors import build_error
from app.output_contract import validate_final_event
from app.schema_registry import SchemaRegistry
from app.storage_client import StorageClient


class IntelligenceService:
    """Interprets recognition events and emits routed attendance payloads."""

    def __init__(
        self,
        *,
        schema_registry: Optional[SchemaRegistry] = None,
        entry_exit_engine: Optional[EntryExitEngine] = None,
        confidence_router: Optional[ConfidenceRouter] = None,
        storage_client: Optional[StorageClient] = None,
    ) -> None:
        self.schemas = schema_registry or SchemaRegistry()
        self.engine = entry_exit_engine or EntryExitEngine()
        self.router = confidence_router or ConfidenceRouter()
        self.storage_client = storage_client

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

    @staticmethod
    def _normalize_student_id(value: Optional[str]) -> str:
        if value is None or value.strip() == "":
            return "UNKNOWN"
        return value

    def process(self, recognition_event: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        trace_id: Optional[str] = None
        try:
            if not isinstance(recognition_event, dict):
                return self._reject(
                    code="ERR_INVALID_PAYLOAD",
                    message="recognition_event must be a JSON object",
                    error_type="OTHER",
                    severity="HIGH",
                )

            trace_id = recognition_event.get("trace_id")
            input_valid, input_error = self.schemas.validate("recognition.schema.json", recognition_event)
            if not input_valid:
                return self._reject(
                    code="ERR_INVALID_INPUT_SCHEMA",
                    message=input_error or "Invalid recognition payload",
                    trace_id=trace_id,
                    context={"schema": "recognition.schema.json"},
                )

            context = context or {}
            camera_id = context.get("camera_id")
            zone = context.get("zone")

            normalized_student_id = self._normalize_student_id(recognition_event.get("student_id"))

            if normalized_student_id == "UNKNOWN":
                interpretation = {
                    "event": "ENTRY",
                    "anomaly_flags": [],
                    "requires_review": False,
                    "is_duplicate": False,
                    "metadata": {},
                }
            else:
                if self.storage_client is not None:
                    recovery = self.storage_client.fetch_by_student(normalized_student_id)
                    if not recovery.get("ok"):
                        error_status = recovery.get("status")
                        error_type = "TIMEOUT" if error_status == "TIMEOUT" else "SERVICE_UNAVAILABLE"
                        context_err: Dict[str, Any] = {"endpoint": "/fetch-by-student"}
                        if recovery.get("http_status") is not None:
                            context_err["http_status"] = int(recovery["http_status"])
                        return self._reject(
                            code="ERR_STORAGE_UNAVAILABLE",
                            message=f"Storage recovery failed for student {normalized_student_id}: {recovery.get('error') or recovery.get('reason')}",
                            trace_id=trace_id,
                            error_type=error_type,
                            severity="HIGH",
                            context=context_err,
                        )
                    self.engine.restore_state_from_history(normalized_student_id, recovery.get("events", []))

                # Interpret event without committing state
                interpretation = self.engine.interpret(
                    trace_id=recognition_event["trace_id"],
                    student_id=normalized_student_id,
                    timestamp=recognition_event["timestamp"],
                    commit=False,
                )

            route = self.router.route(
                confidence=float(recognition_event["confidence"]),
                requires_review=bool(interpretation["requires_review"]),
                is_duplicate=bool(interpretation["is_duplicate"]),
                student_id=normalized_student_id,
            )

            # Phase 6 rule: REJECT is treated as unknown identity.
            effective_student_id = "UNKNOWN" if route["status"] == "REJECT" else normalized_student_id

            # Confidence-gated state management:
            # Commit new state only if final routing status is AUTO, not duplicate, and student is known.
            if (
                route["status"] == "AUTO"
                and not interpretation["is_duplicate"]
                and normalized_student_id != "UNKNOWN"
            ):
                self.engine.commit_state(
                    student_id=normalized_student_id,
                    event=interpretation["event"],
                    timestamp=recognition_event["timestamp"],
                    trace_id=recognition_event["trace_id"],
                )

            intelligence_event: Dict[str, Any] = {
                "trace_id": recognition_event["trace_id"],
                "timestamp": recognition_event["timestamp"],
                "student_id": effective_student_id,
                "event": interpretation["event"],
                "confidence": recognition_event["confidence"],
                "anomaly_flags": interpretation["anomaly_flags"],
                "requires_review": interpretation["requires_review"],
            }
            if camera_id is not None:
                intelligence_event["camera_id"] = camera_id
            if zone is not None:
                intelligence_event["zone"] = zone
            if interpretation["metadata"]:
                intelligence_event["metadata"] = interpretation["metadata"]

            intelligence_valid, intelligence_error = self.schemas.validate(
                "intelligence.schema.json", intelligence_event
            )
            if not intelligence_valid:
                return self._reject(
                    code="ERR_INVALID_INTELLIGENCE_SCHEMA",
                    message=intelligence_error or "Invalid intelligence output",
                    trace_id=trace_id,
                    context={"schema": "intelligence.schema.json"},
                )

            confidence_event: Dict[str, Any] = {
                "trace_id": recognition_event["trace_id"],
                "timestamp": recognition_event["timestamp"],
                "student_id": effective_student_id,
                "event": interpretation["event"],
                "confidence": recognition_event["confidence"],
                "routing_decision": route["status"],
                "thresholds_applied": {
                    "auto_threshold": self.router.AUTO_THRESHOLD,
                    "review_threshold": self.router.REVIEW_THRESHOLD,
                },
                "reason": route["reason"],
                "anomalies": interpretation["anomaly_flags"],
            }

            confidence_valid, confidence_error = self.schemas.validate(
                "confidence.schema.json", confidence_event
            )
            if not confidence_valid:
                return self._reject(
                    code="ERR_INVALID_CONFIDENCE_SCHEMA",
                    message=confidence_error or "Invalid confidence output",
                    trace_id=trace_id,
                    context={"schema": "confidence.schema.json"},
                )

            storage_event: Dict[str, Any] = {
                "trace_id": recognition_event["trace_id"],
                "timestamp": recognition_event["timestamp"],
                "student_id": effective_student_id,
                "event": interpretation["event"],
                "confidence": recognition_event["confidence"],
                "status": route["status"],
                "source_service": "confidence_service",
                "anomaly_flags": interpretation["anomaly_flags"],
                "metadata": {
                    "correction_applied": False,
                    "original_student_id": recognition_event.get("student_id"),
                    "operator_id": None,
                    "correction_notes": "",
                },
            }
            if camera_id is not None:
                storage_event["camera_id"] = camera_id
            if zone is not None:
                storage_event["zone"] = zone

            storage_valid, storage_error = self.schemas.validate("storage.schema.json", storage_event)
            if not storage_valid:
                return self._reject(
                    code="ERR_INVALID_STORAGE_SCHEMA",
                    message=storage_error or "Invalid storage output",
                    trace_id=trace_id,
                    context={"schema": "storage.schema.json"},
                )

            final_event: Dict[str, Any] = {
                "trace_id": recognition_event["trace_id"],
                "student_id": effective_student_id,
                "event": interpretation["event"],
                "confidence": recognition_event["confidence"],
                "status": route["status"],
                "timestamp": recognition_event["timestamp"],
            }
            final_valid, final_error = validate_final_event(final_event)
            if not final_valid:
                return self._reject(
                    code="ERR_INVALID_OUTPUT_CONTRACT",
                    message=final_error or "Invalid final event contract",
                    trace_id=trace_id,
                    context={"contract": "final_pipeline_event"},
                )

            return {
                "ok": True,
                "intelligence_event": intelligence_event,
                "confidence_event": confidence_event,
                "storage_event": storage_event,
                "final_event": final_event,
                "status": {"status": route["status"]},
            }
        except Exception as exc:  # pragma: no cover - defensive safety net
            return self._reject(
                code="ERR_INTELLIGENCE_PROCESSING",
                message=str(exc),
                trace_id=trace_id,
                error_type="OTHER",
                severity="HIGH",
            )
