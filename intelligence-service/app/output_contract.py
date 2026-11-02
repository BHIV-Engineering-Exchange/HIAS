"""Strict final event contract for downstream integration."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from typing_extensions import Literal


class FinalPipelineEvent(BaseModel):
    """Exact output format required by integration consumers."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(pattern=r"^HIAS-[0-9]{8}-[a-f0-9]{8}-[0-9]{6}$")
    student_id: str = Field(pattern=r"^[A-Z0-9]{6,10}$")
    event: Literal["ENTRY", "EXIT"]
    confidence: float = Field(ge=0.0, le=1.0)
    status: Literal["AUTO", "REVIEW", "REJECT"]
    timestamp: str

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_iso8601(cls, value: str) -> str:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        datetime.fromisoformat(normalized)
        return value


def validate_final_event(payload: Dict) -> Tuple[bool, Optional[str]]:
    """Validate final pipeline event with strict required/no-extra rules."""
    try:
        FinalPipelineEvent.model_validate(payload)
        return True, None
    except ValidationError as exc:
        return False, str(exc)
