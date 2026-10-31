"""
Test fixtures for HIAS-Upstream backend tests.

Uses an in-memory SQLite database, clears startup handlers (CosecWorker),
patches open_gate to prevent any hardware interaction, and mocks
Storage Service HTTP client to isolate camera intelligence tests.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import httpx
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app, DUPLICATE_CACHE, REVIEW_QUEUE, SYSTEM_SETTINGS
from app.engine import seed_db
from app import camera_intelligence

# ---------------------------------------------------------------------------
# In-memory test database with StaticPool so all connections share the DB
# ---------------------------------------------------------------------------

_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(
    autocommit=False, autoflush=False, bind=_test_engine
)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """
    FastAPI TestClient backed by an in-memory SQLite database.

    * Startup handlers are cleared (no CosecWorker, no production DB seed).
    * open_gate is patched out to prevent hardware interaction.
    * httpx.AsyncClient is patched to mock the external Storage Service.
    * Global mutable state is reset between tests.
    * Explicit test-only camera student mappings are set (cleared on teardown).
    * Test DB is created, seeded, and torn down per test.
    """
    # Create tables and seed users
    Base.metadata.create_all(bind=_test_engine)
    db = _TestSession()
    seed_db(db)
    db.close()

    # Override FastAPI dependency
    app.dependency_overrides[get_db] = _override_get_db

    # Reset global state
    DUPLICATE_CACHE.clear()
    REVIEW_QUEUE.clear()
    SYSTEM_SETTINGS.update({
        "emergency_mode": False,
        "access_window_start": "07:00",
        "access_window_end": "21:00",
        "require_admin_approval": False,
    })

    # Supply explicit test-only mappings
    camera_intelligence.STUDENT_USER_MAPPING.clear()
    camera_intelligence.STUDENT_USER_MAPPING.update({
        "STU0000001": "S001",
        "STU0000002": "S002",
        "STUNONEX99": "S999",  # Maps to nonexistent HIAS user
    })

    # Remove startup handlers to prevent CosecWorker / production DB access
    saved_startup = list(app.router.on_startup)
    app.router.on_startup.clear()

    def _default_storage_post(url, *args, **kwargs):
        payload = kwargs.get("json", {})
        trace_id = payload.get("trace_id", "HIAS-mock")
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "status": "ACCEPTED",
            "trace_id": trace_id,
            "event_id": f"evt-{trace_id}",
        }
        return resp

    mock_storage_client = AsyncMock()
    mock_storage_client.post.side_effect = _default_storage_post

    with patch("app.main.open_gate") as mock_gate, \
         patch("httpx.AsyncClient") as mock_http_client_cls:
        mock_http_client_cls.return_value.__aenter__.return_value = mock_storage_client
        mock_http_client_cls.return_value.__aexit__.return_value = None

        with TestClient(app, raise_server_exceptions=False) as c:
            # Expose mocks so tests can assert on them or customize responses
            c.mock_open_gate = mock_gate
            c.mock_storage_client = mock_storage_client
            c.mock_storage_post = mock_storage_client.post
            yield c

    # Teardown
    camera_intelligence.STUDENT_USER_MAPPING.clear()
    app.router.on_startup[:] = saved_startup
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=_test_engine)
