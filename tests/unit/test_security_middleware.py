"""
Unit tests for security/middleware.py
Tests:
  - ErrorBoundaryMiddleware captures unhandled exceptions and prevents crashes
  - Headers: X-Trace-ID, nosniff, DENY are added
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from security.middleware import install_security_middlewares


@pytest.fixture
def error_app():
    test_app = FastAPI()
    install_security_middlewares(test_app)

    @test_app.get("/trigger-crash")
    def trigger_crash():
        raise RuntimeError("Simulated unexpected server crash")

    @test_app.get("/normal")
    def normal():
        return {"ok": True}

    return test_app


class TestSecurityMiddleware:
    def test_error_boundary_catches_unhandled_crash(self, error_app):
        client = TestClient(error_app, raise_server_exceptions=False)
        resp = client.get("/trigger-crash")
        assert resp.status_code == 500
        data = resp.json()
        assert data["error"] == "InternalServerError"
        assert "trace_id" in data
        assert "nosniff" in resp.headers.get("x-content-type-options", "")

    def test_normal_response_includes_security_headers(self, error_app):
        client = TestClient(error_app)
        resp = client.get("/normal")
        assert resp.status_code == 200
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
