"""
API — Production Runtime Module
T-GOV-F02 Remediation & Hardening for HIAS Architecture
Exposes fully typed, Pydantic-validated REST endpoints with error boundary protection,
deterministic rule engine integration, and review orchestration.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from evaluation_engine.rule_engine import Decision, Reason, RuleEngine
from task_selector.review_orchestrator import ManualOverrideInput, ReviewAction, ReviewOrchestrator
from security.middleware import install_security_middlewares
from integrations.local_llm_client import LocalLLMClient, LLMAnalysisRequest

# ---------------------------------------------------------------------------
# Strict Inbound & Outbound Schemas
# ---------------------------------------------------------------------------

class AccessInput(BaseModel):
    """Strictly validated access event payload."""
    user_id: str = Field(..., min_length=1, description="Card or resident ID")
    method: Literal["RFID", "FACE", "MANUAL", "PIN"] = Field(..., description="Access verification method")
    device_id: str = Field(..., min_length=1, description="Physical turnstile/gate identifier")


class UserEnrollInput(BaseModel):
    """Strictly validated user enrollment payload."""
    user_id: str = Field(..., min_length=1, description="Unique alphanumeric identifier")
    name: str = Field(..., min_length=1, description="Full name of resident or officer")
    role: str = Field(default="Resident", min_length=1)


class SettingsUpdateInput(BaseModel):
    """Strictly validated settings payload — forbidden from accepting arbitrary keys."""
    emergency_mode: Optional[bool] = None
    access_window_start: Optional[str] = None
    access_window_end: Optional[str] = None
    require_admin_approval: Optional[bool] = None

    model_config = {"extra": "forbid"}


class ProductionEvent(BaseModel):
    """Canonical event structure emitted by the production API."""
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    name: str
    direction: Literal["IN", "OUT"]
    method: str
    decision: Decision
    reason: Reason | str
    device_id: str
    state_hash: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ---------------------------------------------------------------------------
# Application Factory
# ---------------------------------------------------------------------------

def create_production_app() -> FastAPI:
    """Builds and configures the production FastAPI application."""
    app = FastAPI(
        title="HIAS Production Core",
        version="1.0.0",
        description="Hardened, remediated production controller engine for HIAS."
    )

    # CORS Configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Error Boundary & Security Middlewares
    install_security_middlewares(app)

    # State Repositories
    rule_engine = RuleEngine()
    review_orchestrator = ReviewOrchestrator()
    llm_client = LocalLLMClient()

    settings_store: Dict[str, Any] = {
        "emergency_mode": False,
        "access_window_start": "06:00",
        "access_window_end": "23:59",
        "require_admin_approval": False,
    }

    events_log: List[ProductionEvent] = []
    duplicate_cache: Dict[tuple, float] = {}
    duplicate_threshold: float = 2.0  # Anti-passback duplicate suppression window

    # -----------------------------------------------------------------------
    # Endpoints
    # -----------------------------------------------------------------------

    @app.get("/health", status_code=status.HTTP_200_OK)
    async def health_check():
        """Health check probe."""
        return {
            "status": "healthy",
            "service": "hias-production-api",
            "timestamp": datetime.utcnow().isoformat()
        }

    @app.post("/access/event", response_model=ProductionEvent, status_code=status.HTTP_200_OK)
    async def access_event(payload: AccessInput):
        """Processes access attempts with duplicate suppression and rule evaluation."""
        now = time.monotonic()
        dup_key = (payload.user_id, payload.device_id)

        # Duplicate scan suppression
        if dup_key in duplicate_cache:
            if now - duplicate_cache[dup_key] < duplicate_threshold:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Duplicate scan ignored"
                )
        duplicate_cache[dup_key] = now

        # Evaluate access using RuleEngine
        eval_result = rule_engine.evaluate(payload.user_id, settings_store)
        direction = "IN" if "in" in payload.device_id.lower() else "OUT"

        event = ProductionEvent(
            user_id=payload.user_id,
            name=eval_result.display_name,
            direction=direction,
            method=payload.method,
            decision=eval_result.decision,
            reason=eval_result.reason,
            device_id=payload.device_id,
            state_hash=eval_result.state_hash
        )

        if settings_store.get("require_admin_approval", False) and eval_result.decision == Decision.ALLOW:
            event.decision = Decision.REVIEW
            review_orchestrator.enqueue(event.trace_id, event.user_id, event.method, event.device_id)

        events_log.append(event)
        return event

    @app.post("/manual/override", response_model=ProductionEvent, status_code=status.HTTP_200_OK)
    async def manual_override(payload: ManualOverrideInput):
        """Security officer emergency / manual override endpoint."""
        eval_result = rule_engine.evaluate("S100", settings_store)
        event = ProductionEvent(
            user_id="S100",
            name=f"[OVERRIDE] {eval_result.display_name}",
            direction="IN",
            method="MANUAL",
            decision=Decision.ALLOW,
            reason=payload.reason,
            device_id="manual_console_01",
            state_hash=eval_result.state_hash
        )
        events_log.append(event)
        return event

    @app.post("/review/action", status_code=status.HTTP_200_OK)
    async def review_action(payload: ReviewAction):
        """Resolves an enqueued review item with confirm or reject."""
        try:
            resolved = review_orchestrator.resolve(payload)
            return {"status": "success", "item": resolved.model_dump()}
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Review trace_id '{payload.trace_id}' not found"
            )

    @app.get("/review/pending", status_code=status.HTTP_200_OK)
    async def get_pending_reviews():
        """Lists all items currently awaiting review."""
        return review_orchestrator.get_pending()

    @app.get("/settings", status_code=status.HTTP_200_OK)
    async def get_settings():
        """Retrieves active system configuration."""
        return settings_store

    @app.post("/settings", status_code=status.HTTP_200_OK)
    async def update_settings(payload: SettingsUpdateInput):
        """Updates system configuration with strict Pydantic model validation."""
        data = payload.model_dump(exclude_none=True)
        settings_store.update(data)
        return settings_store

    @app.get("/users", status_code=status.HTTP_200_OK)
    async def get_users():
        """Returns all enrolled users in the registry."""
        return [
            {"user_id": uid, "name": u["name"], "role": u["role"]}
            for uid, u in rule_engine.user_registry.items()
        ]

    @app.post("/users", status_code=status.HTTP_200_OK)
    async def enroll_user(payload: UserEnrollInput):
        """Enrolls a new user into the registry."""
        if payload.user_id in rule_engine.user_registry:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User ID already exists"
            )
        rule_engine.user_registry[payload.user_id] = {
            "name": payload.name,
            "role": payload.role
        }
        return {"status": "success", "user_id": payload.user_id}

    @app.get("/events", status_code=status.HTTP_200_OK)
    async def get_events(limit: int = 50):
        """Returns recorded access events."""
        return [e.model_dump() for e in events_log[-limit:]]

    @app.get("/stats/summary", status_code=status.HTTP_200_OK)
    async def get_stats_summary():
        """Returns total granted and denied metrics."""
        total = len(events_log)
        granted = sum(1 for e in events_log if e.decision == Decision.ALLOW)
        denied = sum(1 for e in events_log if e.decision == Decision.DENY)
        review = sum(1 for e in events_log if e.decision == Decision.REVIEW)
        return {
            "total": total,
            "granted": granted,
            "denied": denied,
            "review": review
        }

    @app.post("/audit/llm-analysis", status_code=status.HTTP_200_OK)
    async def run_llm_analysis(req: LLMAnalysisRequest):
        """Requests policy audit or explanation from the local LLM integration."""
        return llm_client.analyze(req)

    return app


app = create_production_app()
