"""
Unit tests for task_selector/review_orchestrator.py
Tests:
  - Enqueue and retrieval of review items
  - Strict confirm/reject actions
  - Schema validation error boundaries
"""
import pytest
from pydantic import ValidationError
from task_selector.review_orchestrator import (
    ReviewOrchestrator,
    ReviewAction,
    ManualOverrideInput,
)


class TestReviewOrchestrator:
    @pytest.fixture
    def orchestrator(self):
        return ReviewOrchestrator()

    def test_enqueue_and_get_pending(self, orchestrator):
        item = orchestrator.enqueue("trace-001", "S001", "FACE", "turnstile_01")
        assert item.status == "pending"
        assert item.trace_id == "trace-001"

        pending = orchestrator.get_pending()
        assert len(pending) == 1
        assert pending[0].trace_id == "trace-001"

    def test_resolve_confirm(self, orchestrator):
        orchestrator.enqueue("trace-002", "S002", "RFID", "gate_in")
        action = ReviewAction(trace_id="trace-002", action="confirm")
        resolved = orchestrator.resolve(action)
        assert resolved.status == "confirmed"
        assert len(orchestrator.get_pending()) == 0

    def test_resolve_reject(self, orchestrator):
        orchestrator.enqueue("trace-003", "S003", "RFID", "gate_in")
        action = ReviewAction(trace_id="trace-003", action="reject")
        resolved = orchestrator.resolve(action)
        assert resolved.status == "rejected"
        assert len(orchestrator.get_pending()) == 0

    def test_resolve_nonexistent_trace_raises_key_error(self, orchestrator):
        action = ReviewAction(trace_id="missing-trace", action="confirm")
        with pytest.raises(KeyError):
            orchestrator.resolve(action)

    def test_review_action_invalid_action_literal_raises(self):
        with pytest.raises(ValidationError):
            ReviewAction(trace_id="trace-123", action="approve")  # Not confirm or reject

    def test_manual_override_input_defaults(self):
        obj = ManualOverrideInput()
        assert obj.reason == "No reason provided"
        assert obj.operator_id == "admin"

    def test_manual_override_input_empty_reason_raises(self):
        with pytest.raises(ValidationError):
            ManualOverrideInput(reason="")
