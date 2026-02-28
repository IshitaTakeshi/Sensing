"""Tests for websocket concurrency and connection lifecycle."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from server.broadcaster import _enqueue_message
from server.main import _send_messages_until_disconnect, app
from tests.server.conftest import ControlledGNSSReader
from tests.server.helpers import make_gnss


def test_multiple_clients(gnss_controller: ControlledGNSSReader) -> None:
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws") as socket_one,
        client.websocket_connect("/ws") as socket_two,
    ):
        gnss_controller.message_queue.put(make_gnss(has_vtg=True, vtg_valid=True))
        assert socket_one.receive_json()["type"] == "gnss"
        assert socket_two.receive_json()["type"] == "gnss"


def test_drop_oldest_overflow() -> None:
    message_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=2)
    _enqueue_message(message_queue, "message_one")
    _enqueue_message(message_queue, "message_two")
    _enqueue_message(message_queue, "message_three")
    assert message_queue.qsize() == 2
    assert message_queue.get_nowait() == "message_two"
    assert message_queue.get_nowait() == "message_three"


def test_timeout_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("server.main._TIMEOUT_SECONDS", 0.05)
    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect("/ws") as websocket,
    ):
        websocket.receive_json()
    assert exc_info.value.code == 1001


def test_client_disconnect_silent() -> None:
    class MockWebSocket:
        async def send_text(self, _text: str) -> None:
            raise WebSocketDisconnect(code=1000)

    async def _run() -> None:
        message_queue = MagicMock(spec=asyncio.Queue)
        message_queue.get = AsyncMock(return_value="message")
        websocket = MockWebSocket()
        await _send_messages_until_disconnect(message_queue, websocket)  # type: ignore[arg-type]

    asyncio.run(_run())
