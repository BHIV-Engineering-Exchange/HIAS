"""Deterministic trace id generation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional


def _parse_iso8601(timestamp: str) -> datetime:
    normalized = timestamp
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return datetime.fromisoformat(normalized)


class TraceGenerator:
    """Generates stable trace ids from camera event content."""

    def generate(
        self,
        *,
        timestamp: str,
        camera_id: str,
        image_data: Dict[str, Any],
        sequence_num: Optional[int] = None,
    ) -> str:
        event_dt = _parse_iso8601(timestamp)
        date_part = event_dt.strftime("%Y%m%d")
        canonical_image = json.dumps(image_data, sort_keys=True, separators=(",", ":"))
        seed = f"{camera_id}|{timestamp}|{canonical_image}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        camera_hash = digest[:8]

        if sequence_num is None:
            sequence_num = (int(digest[8:16], 16) % 999999) + 1

        sequence_num = max(1, min(999999, int(sequence_num)))
        return f"HIAS-{date_part}-{camera_hash}-{sequence_num:06d}"
