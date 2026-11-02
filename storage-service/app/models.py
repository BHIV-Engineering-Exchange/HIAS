"""Lightweight storage models used for typing and document shaping.

The MongoDB implementation stores plain documents, so these dataclasses are
kept only as a structured representation of the storage records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Event:
    event_id: str
    trace_id: str
    student_id: str
    event: str
    confidence: float
    status: str
    source_service: str
    camera_id: Optional[str] = None
    zone: Optional[str] = None
    timestamp: Optional[datetime] = None
    created_at: Optional[datetime] = None
    hash: Optional[str] = None
    prev_hash: Optional[str] = None
    anomaly_flags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "student_id": self.student_id,
            "event": self.event,
            "confidence": self.confidence,
            "status": self.status,
            "source_service": self.source_service,
            "camera_id": self.camera_id,
            "zone": self.zone,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "hash": self.hash,
            "prev_hash": self.prev_hash,
            "anomaly_flags": self.anomaly_flags,
            "metadata": self.metadata,
        }


@dataclass
class HashChainRecord:
    record_id: str
    event_id: str
    current_hash: str
    prev_hash: str
    is_verified: bool = False
    verification_timestamp: Optional[datetime] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "event_id": self.event_id,
            "current_hash": self.current_hash,
            "prev_hash": self.prev_hash,
            "is_verified": self.is_verified,
            "verification_timestamp": self.verification_timestamp.isoformat() if self.verification_timestamp else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class StorageStats:
    stat_id: str
    total_events: int = 0
    total_students: int = 0
    last_event_timestamp: Optional[datetime] = None
    hash_chain_verified: bool = True
    last_verification_timestamp: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stat_id": self.stat_id,
            "total_events": self.total_events,
            "total_students": self.total_students,
            "last_event_timestamp": self.last_event_timestamp.isoformat() if self.last_event_timestamp else None,
            "hash_chain_verified": self.hash_chain_verified,
            "last_verification_timestamp": self.last_verification_timestamp.isoformat() if self.last_verification_timestamp else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
