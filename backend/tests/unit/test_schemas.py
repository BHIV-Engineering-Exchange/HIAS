"""
Unit tests for app/schemas.py — Pydantic model validation.
"""
import pytest
from pydantic import ValidationError
from app.schemas import (
    AccessInput, ReviewAction, ManualOverrideInput,
    UserEnrollInput, SettingsUpdateInput, ControllerEvent,
    Method, Decision, Reason, Direction
)
import uuid


class TestAccessInput:
    def test_valid_payload(self):
        obj = AccessInput(user_id="S001", method="RFID", device_id="door_01")
        assert obj.method == Method.RFID

    def test_invalid_method_enum_raises(self):
        with pytest.raises(ValidationError):
            AccessInput(user_id="S001", method="FINGER", device_id="door_01")

    def test_empty_user_id_raises(self):
        with pytest.raises(ValidationError):
            AccessInput(user_id="", method="RFID", device_id="door_01")

    def test_empty_device_id_raises(self):
        with pytest.raises(ValidationError):
            AccessInput(user_id="S001", method="RFID", device_id="")

    def test_missing_field_raises(self):
        with pytest.raises(ValidationError):
            AccessInput(user_id="S001", method="RFID")


class TestReviewAction:
    def test_confirm_action_valid(self):
        obj = ReviewAction(trace_id="abc-123", action="confirm")
        assert obj.action == "confirm"

    def test_reject_action_valid(self):
        obj = ReviewAction(trace_id="abc-123", action="reject")
        assert obj.action == "reject"

    def test_invalid_action_literal_raises(self):
        with pytest.raises(ValidationError):
            ReviewAction(trace_id="abc-123", action="approve")

    def test_empty_trace_id_raises(self):
        with pytest.raises(ValidationError):
            ReviewAction(trace_id="", action="confirm")


class TestManualOverrideInput:
    def test_valid_with_reason(self):
        obj = ManualOverrideInput(reason="Testing override")
        assert obj.reason == "Testing override"

    def test_default_reason_applied(self):
        obj = ManualOverrideInput()
        assert obj.reason == "No reason provided"

    def test_empty_reason_raises(self):
        with pytest.raises(ValidationError):
            ManualOverrideInput(reason="")


class TestUserEnrollInput:
    def test_valid_user(self):
        obj = UserEnrollInput(user_id="S010", name="Test User")
        assert obj.role == "Resident"

    def test_custom_role(self):
        obj = UserEnrollInput(user_id="S010", name="Admin User", role="Admin")
        assert obj.role == "Admin"

    def test_empty_user_id_raises(self):
        with pytest.raises(ValidationError):
            UserEnrollInput(user_id="", name="Test")

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError):
            UserEnrollInput(user_id="S010", name="")


class TestSettingsUpdateInput:
    def test_valid_partial_update(self):
        obj = SettingsUpdateInput(emergency_mode=True)
        assert obj.emergency_mode is True

    def test_all_fields(self):
        obj = SettingsUpdateInput(
            emergency_mode=False,
            access_window_start="08:00",
            access_window_end="20:00",
            require_admin_approval=True
        )
        assert obj.access_window_start == "08:00"

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            SettingsUpdateInput(unknown_field="bad")

    def test_none_values_excluded_on_dump(self):
        obj = SettingsUpdateInput(emergency_mode=True)
        data = obj.model_dump(exclude_none=True)
        assert "access_window_start" not in data
        assert data["emergency_mode"] is True


class TestControllerEvent:
    def test_defaults_generated(self):
        obj = ControllerEvent(
            user_id="S001", name="Test", direction=Direction.IN,
            method=Method.RFID, decision=Decision.ALLOW,
            reason=Reason.VALID, device_id="door_01"
        )
        assert obj.trace_id != ""
        # Ensure it's a valid UUID
        uuid.UUID(obj.trace_id)
        assert obj.timestamp != ""
