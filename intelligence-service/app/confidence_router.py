"""Deterministic confidence routing."""

from __future__ import annotations

from typing import Dict


class ConfidenceRouter:
    """Apply confidence thresholds and edge-case overrides."""

    AUTO_THRESHOLD = 0.90
    REVIEW_THRESHOLD = 0.70

    def route(
        self,
        *,
        confidence: float,
        requires_review: bool,
        is_duplicate: bool,
        student_id: str,
    ) -> Dict[str, str]:
        if student_id == "UNKNOWN":
            return {"status": "REJECT", "reason": "unknown_identity"}
        if is_duplicate:
            return {"status": "REJECT", "reason": "duplicate_detection"}

        if confidence >= self.AUTO_THRESHOLD and not requires_review:
            return {"status": "AUTO", "reason": "confidence_above_auto_threshold"}
        if confidence >= self.REVIEW_THRESHOLD:
            return {"status": "REVIEW", "reason": "confidence_in_review_band"}
        return {"status": "REJECT", "reason": "confidence_below_review_threshold"}
