"""
Reference: How to write a compliant event to the HIAS Storage Service.

Any service (confidence_service, human_loop_service) must:
1. Build a payload matching storage.schema.json
2. POST to /store-event
3. Handle ACCEPTED / REJECTED response
"""

import requests

STORAGE_URL = "http://127.0.0.1:8005"


def store_event(payload: dict) -> dict:
    """Send a validated event to the storage gateway. Returns response dict."""
    response = requests.post(f"{STORAGE_URL}/store-event", json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_by_trace(trace_id: str) -> dict:
    response = requests.get(f"{STORAGE_URL}/fetch-by-trace", params={"trace_id": trace_id}, timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_by_student(student_id: str, date: str = None, status: str = None) -> dict:
    params = {"student_id": student_id}
    if date:
        params["date"] = date
    if status:
        params["status"] = status
    response = requests.get(f"{STORAGE_URL}/fetch-by-student", params=params, timeout=10)
    response.raise_for_status()
    return response.json()


# ── Example usage ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sample_payload = {
        "trace_id": "HIAS-20260429-abcdef12-000001",
        "timestamp": "2026-04-29T13:15:00Z",
        "student_id": "STU123456",
        "event": "ENTRY",
        "confidence": 0.92,
        "status": "AUTO",
        "source_service": "confidence_service",
        "camera_id": "GATE-MAIN",
        "zone": "GATE_MAIN",
    }

    result = store_event(sample_payload)
    print("Store result:", result)

    if result.get("status") == "ACCEPTED":
        trace_result = fetch_by_trace(sample_payload["trace_id"])
        print("Fetch by trace:", trace_result)
