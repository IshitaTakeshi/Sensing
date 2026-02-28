"""FastAPI web server for real-time sensor visualization."""

import asyncio
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from server.broadcaster import add_subscriber, remove_subscriber
from server.sensors import run_gnss_loop, run_imu_loop

__all__ = ["application"]

_STATIC_DIRECTORY = Path(__file__).parent / "static"
_QUEUE_MAXIMUM_SIZE = 10
_TIMEOUT_SECONDS = 5.0


@asynccontextmanager
async def _lifespan(_application: FastAPI) -> AsyncIterator[None]:
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=2)
    loop.run_in_executor(executor, run_gnss_loop, loop)
    loop.run_in_executor(executor, run_imu_loop, loop)
    yield
    executor.shutdown(wait=False)


application = FastAPI(lifespan=_lifespan)


async def _send_messages_until_disconnect(
    queue: asyncio.Queue[str], websocket: WebSocket
) -> None:
    try:
        while True:
            message = await asyncio.wait_for(queue.get(), timeout=_TIMEOUT_SECONDS)
            await websocket.send_text(message)
    except TimeoutError:
        await websocket.close(code=1001)
    except WebSocketDisconnect:
        pass


@application.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Streams sensor JSON messages to a WebSocket client."""
    await websocket.accept()
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_QUEUE_MAXIMUM_SIZE)
    add_subscriber(queue)

    try:
        await _send_messages_until_disconnect(queue, websocket)
    finally:
        remove_subscriber(queue)


application.mount(
    "/",
    StaticFiles(directory=_STATIC_DIRECTORY, html=True),
    name="static",
)
