"""Tests for websocket concurrency and connection lifecycle."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from server.main import _enqueue, _forward_queue_to_websocket, app
from tests.server.conftest import ControlledGNSSReader
from tests.server.helpers import make_gnss


def test_multiple_clients(gnss_controller: ControlledGNSSReader) -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket_one:
            with client.websocket_connect("/ws") as socket_two:
                gnss_controller.message_queue.put(make_gnss(has_vtg=True, vtg_valid=True))
                assert socket_one.receive_json()["type"] == "gnss"
                assert socket_two.receive_json()["type"] == "gnss"


def test_drop_oldest_overflow() -> None:
    message_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=2)
    _enqueue(message_queue, "message_one")
    _enqueue(message_queue, "message_two")
    _enqueue(message_queue, "message_three")

    assert message_queue.qsize() == 2
    assert message_queue.get_nowait() == "message_two"
    assert message_queue.get_nowait() == "message_three"


def test_timeout_disconnect() -> None:
    class MockWebSocket:
        async def close(self, code: int) -> None:
            self.code = code

    async def execute_test() -> None:
        message_queue = MagicMock(spec=asyncio.Queue)
        message_queue.get = AsyncMock(side_effect=TimeoutError)
        websocket = MockWebSocket()
        await _forward_queue_to_websocket(message_queue, websocket)  # type: ignore
        assert getattr(websocket, "code", None) == 1001

    asyncio.run(execute_test())


def test_client_disconnect_silent() -> None:
    class MockWebSocket:
        async def send_text(self, text: str) -> None:
            raise WebSocketDisconnect(code=1000)

    async def execute_test() -> None:
        message_queue = MagicMock(spec=asyncio.Queue)
        message_queue.get = AsyncMock(return_value="message")
        websocket = MockWebSocket()
        await _forward_queue_to_websocket(message_queue, websocket)  # type: ignore

    asyncio.run(execute_test())
