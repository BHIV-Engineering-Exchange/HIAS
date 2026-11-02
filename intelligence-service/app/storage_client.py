"""HTTP Client for interacting with the HIAS Storage Service."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_STORAGE_URL = "http://127.0.0.1:8005"
DEFAULT_TIMEOUT_SECONDS = 5.0


class StorageClient:
    """Client for interacting with storage-service (reading history & submitting events)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv("STORAGE_SERVICE_URL")
            or os.getenv("STORAGE_URL")
            or DEFAULT_STORAGE_URL
        ).rstrip("/")

        timeout_env = os.getenv("STORAGE_REQUEST_TIMEOUT")
        if timeout is not None:
            self.timeout = float(timeout)
        elif timeout_env:
            self.timeout = float(timeout_env)
        else:
            self.timeout = DEFAULT_TIMEOUT_SECONDS

        self.session = session or requests.Session()

    def store_event(self, storage_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Submit storage_event payload to storage-service POST /store-event.

        Validates client-side constraints (e.g. unknown identities / REJECT status)
        and verifies HTTP response codes and Storage status ('ACCEPTED' vs 'REJECTED').
        """
        trace_id = storage_event.get("trace_id")
        student_id = storage_event.get("student_id")
        status = storage_event.get("status")

        # Guard: Check for UNKNOWN student_id
        if student_id == "UNKNOWN":
            logger.warning(
                "Skipping storage for event %s: student_id is UNKNOWN (does not meet confirmed storage contract)",
                trace_id,
            )
            return {
                "success": False,
                "status": "SKIPPED",
                "reason": "Cannot store event with unknown student_id (UNKNOWN): Storage requires confirmed student ID",
                "trace_id": trace_id,
            }

        # Guard: Check for REJECT status
        if status == "REJECT":
            logger.warning(
                "Skipping storage for event %s: status is REJECT (unconfirmed pipeline event)",
                trace_id,
            )
            return {
                "success": False,
                "status": "SKIPPED",
                "reason": "Cannot store REJECT event: Unconfirmed events must not be persisted to append-only storage",
                "trace_id": trace_id,
            }

        url = f"{self.base_url}/store-event"
        try:
            response = self.session.post(url, json=storage_event, timeout=self.timeout)
        except requests.exceptions.Timeout as exc:
            logger.error("Storage service timed out at %s for trace %s: %s", url, trace_id, exc)
            return {
                "success": False,
                "status": "TIMEOUT",
                "reason": f"Storage request timed out after {self.timeout}s: {str(exc)}",
                "trace_id": trace_id,
            }
        except requests.exceptions.RequestException as exc:
            logger.error("Storage service connection error at %s for trace %s: %s", url, trace_id, exc)
            return {
                "success": False,
                "status": "UNREACHABLE",
                "reason": f"Storage service unreachable at {url}: {str(exc)}",
                "trace_id": trace_id,
            }

        # Inspect HTTP response code
        if response.status_code != 200:
            logger.error(
                "Storage service returned HTTP %s for trace %s: %s",
                response.status_code,
                trace_id,
                response.text,
            )
            return {
                "success": False,
                "status": "HTTP_ERROR",
                "http_status": response.status_code,
                "reason": f"Storage service returned HTTP {response.status_code}: {response.text}",
                "trace_id": trace_id,
            }

        try:
            body = response.json()
        except ValueError as exc:
            logger.error("Invalid JSON response from storage service: %s", exc)
            return {
                "success": False,
                "status": "INVALID_RESPONSE",
                "reason": f"Storage service returned invalid JSON: {str(exc)}",
                "trace_id": trace_id,
            }

        storage_status = body.get("status")
        if storage_status == "ACCEPTED":
            logger.info("Storage service accepted event %s: event_id=%s", trace_id, body.get("event_id"))
            return {
                "success": True,
                "status": "ACCEPTED",
                "event_id": body.get("event_id"),
                "hash": body.get("hash"),
                "prev_hash": body.get("prev_hash"),
                "trace_id": trace_id,
            }

        # Storage explicitly returned REJECTED (e.g. duplicate trace_id or validation error)
        logger.warning(
            "Storage service rejected event %s: %s",
            trace_id,
            body.get("reason"),
        )
        return {
            "success": False,
            "status": "REJECTED",
            "reason": body.get("reason") or "Storage service rejected event",
            "trace_id": trace_id,
        }

    def fetch_by_student(
        self,
        student_id: str,
        date: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch stored event history for a student via GET /fetch-by-student.

        Queries the storage service with bounded timeout and returns a structured
        result containing the event list or an explicit error outcome.
        """
        if not student_id or not isinstance(student_id, str):
            return {
                "ok": False,
                "success": False,
                "status": "INVALID_STUDENT_ID",
                "error": "student_id must be a non-empty string",
                "events": [],
                "total_count": 0,
                "student_id": student_id,
            }

        url = f"{self.base_url}/fetch-by-student"
        params: Dict[str, str] = {"student_id": student_id}
        if date:
            params["date"] = date
        if status:
            params["status"] = status

        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
        except requests.exceptions.Timeout as exc:
            logger.error(
                "Storage service timed out fetching history for student %s: %s",
                student_id,
                exc,
            )
            return {
                "ok": False,
                "success": False,
                "status": "TIMEOUT",
                "error": f"Storage request timed out after {self.timeout}s: {str(exc)}",
                "student_id": student_id,
                "events": [],
                "total_count": 0,
            }
        except requests.exceptions.RequestException as exc:
            logger.error(
                "Storage service unreachable when fetching history for student %s: %s",
                student_id,
                exc,
            )
            return {
                "ok": False,
                "success": False,
                "status": "UNREACHABLE",
                "error": f"Storage service unreachable at {url}: {str(exc)}",
                "student_id": student_id,
                "events": [],
                "total_count": 0,
            }

        if response.status_code != 200:
            logger.error(
                "Storage service returned HTTP %s for student %s: %s",
                response.status_code,
                student_id,
                response.text,
            )
            return {
                "ok": False,
                "success": False,
                "status": "HTTP_ERROR",
                "http_status": response.status_code,
                "error": f"Storage service returned HTTP {response.status_code}: {response.text}",
                "student_id": student_id,
                "events": [],
                "total_count": 0,
            }

        try:
            body = response.json()
        except ValueError as exc:
            logger.error(
                "Invalid JSON from storage service for student %s: %s",
                student_id,
                exc,
            )
            return {
                "ok": False,
                "success": False,
                "status": "INVALID_RESPONSE",
                "error": f"Storage service returned invalid JSON: {str(exc)}",
                "student_id": student_id,
                "events": [],
                "total_count": 0,
            }

        if not isinstance(body, dict) or "events" not in body or not isinstance(body["events"], list):
            logger.error(
                "Malformed response payload from storage service for student %s: %s",
                student_id,
                body,
            )
            return {
                "ok": False,
                "success": False,
                "status": "INVALID_RESPONSE",
                "error": "Storage service response missing valid 'events' array",
                "student_id": student_id,
                "events": [],
                "total_count": 0,
            }

        events = body.get("events", [])
        total_count = body.get("total_count", len(events))
        return {
            "ok": True,
            "success": True,
            "status": "OK",
            "events": events,
            "total_count": total_count,
            "student_id": student_id,
        }

