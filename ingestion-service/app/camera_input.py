"""Deterministic camera event simulator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional


class CameraEventSimulator:
    """Generates stable camera payloads for simulation and test runs."""

    def __init__(self, camera_id: str = "GATE-MAIN", zone: str = "GATE_MAIN") -> None:
        self.camera_id = camera_id
        self.zone = zone

    def generate_events(
        self,
        *,
        count: int,
        start_time: Optional[datetime] = None,
        interval_seconds: int = 15,
    ) -> List[Dict]:
        if start_time is None:
            start_time = datetime(2026, 4, 28, 9, 0, 0, tzinfo=timezone.utc)

        payloads: List[Dict] = []
        for index in range(count):
            event_time = start_time + timedelta(seconds=index * interval_seconds)
            payloads.append(
                {
                    "timestamp": event_time.isoformat().replace("+00:00", "Z"),
                    "camera_id": self.camera_id,
                    "zone": self.zone,
                    "sequence_num": index + 1,
                    "image_data": {
                        "format": "jpeg",
                        "size": 12000 + (index * 13),
                        "url": f"sim://{self.camera_id.lower()}/frame-{index + 1:06d}.jpg",
                    },
                }
            )
        return payloads
