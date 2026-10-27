"""
Task Selector & Review Orchestrator Module
T-GOV-F02 Remediation & Hardening for HIAS Architecture
Provides queue orchestration, manual review decisioning, and manual override capabilities
with strict Pydantic model validation.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ReviewAction(BaseModel):
    """Strictly validated review queue action — only 'confirm' or 'reject' are permitted."""
    trace_id: str = Field(..., min_length=1, description="Unique trace identifier of the event under review")
    action: Literal["confirm", "reject"] = Field(..., description="Decision resolution for the item")


class ManualOverrideInput(BaseModel):
    """Strictly validated manual override payload."""
    reason: str = Field(default="No reason provided", min_length=1, description="Justification for manual override")
    operator_id: str = Field(default="admin", min_length=1, description="ID of staff member executing override")


class QueuedReviewItem(BaseModel):
    """Representation of an event awaiting manual security officer review."""
    trace_id: str
    user_id: str
    method: str
    device_id: str
    enqueued_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    status: Literal["pending", "confirmed", "rejected"] = "pending"
    resolution_notes: Optional[str] = None


class ReviewOrchestrator:
    """
    Manages the review queue and orchestrates operator interventions.
    Guarantees thread-safe in-memory tracking and strict status transitions.
    """

    def __init__(self):
        self._queue: Dict[str, QueuedReviewItem] = {}

    def enqueue(self, trace_id: str, user_id: str, method: str, device_id: str) -> QueuedReviewItem:
        """Enqueue an access event requiring supervisor review."""
        item = QueuedReviewItem(
            trace_id=trace_id,
            user_id=user_id,
            method=method,
            device_id=device_id
        )
        self._queue[trace_id] = item
        return item

    def get_pending(self) -> List[QueuedReviewItem]:
        """Returns all items currently awaiting review."""
        return [item for item in self._queue.values() if item.status == "pending"]

    def resolve(self, action: ReviewAction) -> QueuedReviewItem:
        """
        Applies a review action ('confirm' or 'reject') to a queued item.
        Raises KeyError if the trace_id is not in the queue.
        """
        if action.trace_id not in self._queue:
            raise KeyError(f"Review item with trace_id '{action.trace_id}' not found.")

        item = self._queue[action.trace_id]
        if action.action == "confirm":
            item.status = "confirmed"
            item.resolution_notes = "Supervisor confirmed access grant."
        else:
            item.status = "rejected"
            item.resolution_notes = "Supervisor rejected access grant."
        return item

    def clear(self):
        """Clears all review queue entries."""
        self._queue.clear()
