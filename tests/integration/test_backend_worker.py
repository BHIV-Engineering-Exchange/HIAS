"""
Integration tests for CosecWorker loop in app/background.py.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from app.background import CosecWorker
from app.schemas import Method, Decision


@pytest.mark.asyncio
async def test_worker_full_loop_success():
    mock_process_request = MagicMock()
    mock_broadcast = AsyncMock()

    mock_event = MagicMock()
    mock_event.user_id = "S001"
    mock_event.decision = Decision.ALLOW
    mock_process_request.return_value = mock_event

    worker = CosecWorker(mock_process_request, mock_broadcast)
    worker.adapter.fetch_events = AsyncMock(return_value=[
        {
            "index": 200,
            "device_user_id": "12",
            "timestamp": "2023-10-27 15:00:00",
            "method": Method.FACE
        }
    ])

    await worker._loop_once()

    mock_process_request.assert_called_once()
    args, _ = mock_process_request.call_args
    assert args[1] == "S001"
    assert args[2] == Method.FACE
    mock_broadcast.assert_called_once_with(mock_event)
    assert worker.last_index == 200


@pytest.mark.asyncio
async def test_worker_unknown_user_ignored():
    mock_process_request = MagicMock()
    mock_broadcast = AsyncMock()
    worker = CosecWorker(mock_process_request, mock_broadcast)

    worker.adapter.fetch_events = AsyncMock(return_value=[
        {"index": 201, "device_user_id": "UNKNOWN_999", "timestamp": "...", "method": Method.RFID}
    ])

    await worker._loop_once()

    mock_process_request.assert_not_called()
    assert worker.last_index == 0
