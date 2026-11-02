"""Deterministic face detection."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional


class DeterministicFaceDetector:
    """Produces deterministic face detection output from ingestion payload."""

    def detect(self, ingestion_event: Dict[str, Any]) -> Dict[str, Any]:
        image_data = ingestion_event["image_data"]
        image_size = int(image_data["size"])
        image_format = image_data["format"]
        image_url = image_data.get("url", "")
        trace_id = ingestion_event["trace_id"]

        seed = f"{image_format}|{image_size}|{image_url}"
        signature = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        marker = int(signature[:2], 16)

        face_detected = image_size > 0 and (marker % 17 != 0)
        if not face_detected:
            return {"face_detected": False, "face_bbox": None, "signature": signature}

        x = int(signature[2:4], 16) % 480
        y = int(signature[4:6], 16) % 270
        width = 80 + (int(signature[6:8], 16) % 120)
        height = 80 + (int(signature[8:10], 16) % 120)

        return {
            "face_detected": True,
            "face_bbox": {"x": x, "y": y, "width": width, "height": height},
            "signature": signature,
        }
