"""Structured error helpers for intelligence service."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_error(
    *,
    error_code: str,
    severity: str,
    error_type: str,
    error_message: str,
    trace_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    resolution: Optional[str] = None,
) -> Dict[str, Any]:
    payload_seed = {
        "service_name": "intelligence_service",
        "error_code": error_code,
        "trace_id": trace_id,
        "error_message": error_message,
        "context": context or {},
    }
    seed = json.dumps(payload_seed, sort_keys=True, separators=(",", ":"))
    error_id = str(uuid.uuid5(uuid.NAMESPACE_URL, seed))

    error_payload: Dict[str, Any] = {
        "error_id": error_id,
        "trace_id": trace_id,
        "timestamp": utc_now_iso(),
        "error_code": error_code,
        "service_name": "intelligence_service",
        "severity": severity,
        "error_message": error_message,
        "error_type": error_type,
        "context": context or {},
    }
    if resolution:
        error_payload["resolution"] = resolution
    return error_payload
