"""
Evaluation Engine — Rule Engine Module
T-GOV-F02 Remediation & Hardening for HIAS Architecture
Enforces access control rules, time-window constraints, emergency bypass,
and deterministic evaluation with SHA-256 state hashing.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, Field


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REVIEW = "REVIEW"


class Reason(str, Enum):
    VALID = "VALID"
    UNKNOWN = "UNKNOWN"
    TIME_BLOCK = "TIME_BLOCK"
    EMERGENCY = "EMERGENCY"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


class RuleEvaluationResult(BaseModel):
    """Result of rule evaluation containing decision, reason, display name, and audit state."""
    decision: Decision
    reason: Reason
    display_name: str
    state_hash: str
    evaluated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


def is_within_time_window(start_str: str, end_str: str, current_time_str: Optional[str] = None) -> bool:
    """
    Evaluates whether the current time falls inside the [start, end] window.
    Uses minutes-since-midnight arithmetic to safely support:
      - Normal daytime windows (e.g., 07:00 to 21:00)
      - Overnight / midnight-crossing windows (e.g., 22:00 to 06:00)
    """
    if not current_time_str:
        current_time_str = time.strftime("%H:%M")

    try:
        sh, sm = map(int, start_str.strip().split(":"))
        eh, em = map(int, end_str.strip().split(":"))
        ch, cm = map(int, current_time_str.strip().split(":"))
    except (ValueError, AttributeError):
        return False

    start_m = sh * 60 + sm
    end_m = eh * 60 + em
    cur_m = ch * 60 + cm

    if start_m <= end_m:
        # Standard window within the same calendar day
        return start_m <= cur_m <= end_m
    else:
        # Overnight window crossing midnight
        return cur_m >= start_m or cur_m <= end_m


def compute_state_hash(state: Dict[str, Any]) -> str:
    """
    Produces a deterministic SHA-256 hash of the given state dictionary.
    Keys are strictly sorted to ensure absolute hash stability across runs.
    """
    serialized = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class RuleEngine:
    """
    HIAS Core Access Rule Engine
    Evaluates access requests against database state and system settings:
      Rule 0: Emergency Bypass (overrides all restrictions; safe against null users)
      Rule 1: Identity Lookup (blocks unknown credentials)
      Rule 2: Time Window Compliance (enforces curfew / access hours)
    """

    def __init__(self, user_registry: Optional[Dict[str, Dict[str, Any]]] = None):
        # In-memory user registry for standalone evaluation; fallback to defaults
        self.user_registry = user_registry if user_registry is not None else {
            "S001": {"name": "Soham (Resident)", "role": "Resident"},
            "S002": {"name": "Rohan (Resident)", "role": "Resident"},
            "S003": {"name": "Aarav (Resident)", "role": "Resident"},
            "S100": {"name": "Admin / Staff", "role": "Admin"},
        }

    def evaluate(
        self,
        user_id: str,
        settings: Optional[Dict[str, Any]] = None,
        simulated_time: Optional[str] = None
    ) -> RuleEvaluationResult:
        """
        Executes access rules deterministically.
        Guarantees zero crashes on unknown users or None settings.
        """
        cfg = settings or {
            "emergency_mode": False,
            "access_window_start": "07:00",
            "access_window_end": "21:00",
        }

        # Safe identity resolution prior to rule checks (Bug 1 & 2 remediation)
        user_record = self.user_registry.get(user_id)
        raw_name = user_record["name"] if user_record else "Unknown User"

        # Rule 0: Emergency Bypass
        if cfg.get("emergency_mode", False):
            display_name = f"[EMERGENCY] {raw_name}"
            state = {
                "user_id": user_id,
                "decision": Decision.ALLOW.value,
                "reason": Reason.VALID.value,
                "rule": "RULE_0_EMERGENCY",
                "emergency": True
            }
            return RuleEvaluationResult(
                decision=Decision.ALLOW,
                reason=Reason.VALID,
                display_name=display_name,
                state_hash=compute_state_hash(state)
            )

        # Rule 1: Unknown User Check
        if not user_record:
            state = {
                "user_id": user_id,
                "decision": Decision.DENY.value,
                "reason": Reason.UNKNOWN.value,
                "rule": "RULE_1_IDENTITY_LOOKUP"
            }
            return RuleEvaluationResult(
                decision=Decision.DENY,
                reason=Reason.UNKNOWN,
                display_name="Unknown User",
                state_hash=compute_state_hash(state)
            )

        # Rule 2: Access Window Verification
        win_start = cfg.get("access_window_start", "07:00")
        win_end = cfg.get("access_window_end", "21:00")
        if not is_within_time_window(win_start, win_end, current_time_str=simulated_time):
            state = {
                "user_id": user_id,
                "decision": Decision.DENY.value,
                "reason": Reason.TIME_BLOCK.value,
                "rule": "RULE_2_TIME_WINDOW",
                "window": f"{win_start}-{win_end}"
            }
            return RuleEvaluationResult(
                decision=Decision.DENY,
                reason=Reason.TIME_BLOCK,
                display_name=raw_name,
                state_hash=compute_state_hash(state)
            )

        # Rule 3: Valid Access Grant
        state = {
            "user_id": user_id,
            "decision": Decision.ALLOW.value,
            "reason": Reason.VALID.value,
            "rule": "RULE_3_GRANT_ACCESS"
        }
        return RuleEvaluationResult(
            decision=Decision.ALLOW,
            reason=Reason.VALID,
            display_name=raw_name,
            state_hash=compute_state_hash(state)
        )
