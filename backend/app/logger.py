# Event logger — trace_id-aware audit trail
# Vijay Dhawan (Logs/Trace module) consumes these outputs

import json
import os
import threading
import requests
from datetime import datetime

LOGS_SERVICE_URL = "http://127.0.0.1:8001/events"

def _async_post(url: str, data: dict, fail_prefix: str):
    def _send():
        try:
            requests.post(url, json=data, timeout=1)
        except Exception as e:
            pass
    threading.Thread(target=_send, daemon=True).start()

def log_event(event: dict) -> None:
    """
    Forward a canonical controller event to the Truth Layer (Logging Service).
    """
    _async_post(LOGS_SERVICE_URL, event, "EVENT_LOG_FAIL")
    print(f"[EVENT_LOG] trace_id={event.get('trace_id')} | "
          f"decision={event.get('decision')} | "
          f"user_id={event.get('user_id')}")


def log_relay(trace_id: str, user_id: str) -> None:
    """
    Forward a relay trigger event to the Truth Layer.
    """
    relay_entry = {
        "type": "RELAY_TRIGGER",
        "trace_id": trace_id,
        "user_id": user_id,
        "timestamp": datetime.now().isoformat(),
    }
    _async_post(LOGS_SERVICE_URL, relay_entry, "RELAY_LOG_FAIL")


