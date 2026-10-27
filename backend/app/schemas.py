# Canonical event schema for all HIAS controller events
from datetime import datetime
from typing import Literal
import uuid
from enum import Enum
from pydantic import BaseModel, Field


class Direction(str, Enum):
    IN = "IN"
    OUT = "OUT"


class Method(str, Enum):
    RFID = "RFID"
    FACE = "FACE"
    MANUAL = "MANUAL"


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REVIEW = "REVIEW"


class Reason(str, Enum):
    VALID = "VALID"
    UNKNOWN = "UNKNOWN"
    TIME_BLOCK = "TIME_BLOCK"


# --- Inbound Payloads ---

class AccessInput(BaseModel):
    """Strictly validated inbound access event payload."""
    user_id: str = Field(..., min_length=1)
    method: Method
    device_id: str = Field(..., min_length=1)


class ReviewAction(BaseModel):
    """Strictly validated review queue action — only 'confirm' or 'reject' are legal."""
    trace_id: str = Field(..., min_length=1)
    action: Literal["confirm", "reject"]


class ManualOverrideInput(BaseModel):
    """Strictly validated manual override payload."""
    reason: str = Field(default="No reason provided", min_length=1)


class UserEnrollInput(BaseModel):
    """Strictly validated user enrolment payload."""
    user_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    role: str = Field(default="Resident")


class SettingsUpdateInput(BaseModel):
    """Strictly validated settings update payload."""
    emergency_mode: bool | None = None
    access_window_start: str | None = None
    access_window_end: str | None = None
    require_admin_approval: bool | None = None

    model_config = {"extra": "forbid"}


# --- Canonical Event ---

class ControllerEvent(BaseModel):
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    name: str
    direction: Direction
    method: Method
    decision: Decision
    reason: Reason | str
    device_id: str

    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
