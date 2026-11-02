"""Deterministic student matching from face signature."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional


class DeterministicStudentMatcher:
    """Produces deterministic student_id and confidence values."""

    def match(
        self,
        *,
        trace_id: str,
        signature: str,
        face_detected: bool,
        image_size: int,
    ) -> Dict[str, Any]:
        if not face_detected:
            return {"student_id": None, "confidence": 0.0, "similar_candidates": []}

        # Deterministic confidence range [0.00, 1.00] derived from image size.
        confidence = round((image_size % 101) / 100.0, 2)
        # Student ID based on signature only (not trace_id) for cross-event consistency
        digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()

        if confidence < 0.35:
            return {"student_id": None, "confidence": confidence, "similar_candidates": []}

        base_number = (int(digest[8:16], 16) % 900000) + 100000
        student_id = f"STU{base_number:06d}"

        candidates: List[Dict[str, Any]] = []
        if confidence < 0.90:
            for idx in range(1, 4):
                candidate_number = ((base_number + (idx * 137)) % 900000) + 100000
                candidate_confidence = round(max(0.0, confidence - (0.05 * idx)), 2)
                candidates.append(
                    {"student_id": f"STU{candidate_number:06d}", "confidence": candidate_confidence}
                )

        return {"student_id": student_id, "confidence": confidence, "similar_candidates": candidates}
