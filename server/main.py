"""FastAPI web server for real-time GNSS and IMU sensor visualization.

Start with::

    uvicorn server.main:app --host 0.0.0.0 --port 8000

Then open ``http://<host>:8000/`` in a browser to access the dashboard.
WebSocket clients connect to ``ws://<host>:8000/ws`` and receive a stream
of JSON messages -- one ``type="gnss"`` message per GGA sentence (~1 Hz) and
one ``type="imu"`` message every fifth IMU sample (~20 Hz).
"""

import asyncio
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, asynccontextmanager, nullcontext
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from sensing.gnss import GNSSReader
from sensing.imu import IMUReader
from sensing.nmea.types import GGAData
from sensing.ntrip import NTRIPClient, NTRIPConfig
from server.broadcaster import add_subscriber, remove_subscriber
from server.config import load_ntrip_config
from server.sensors import run_gnss_loop, run_imu_loop

__all__ = ["app"]

_STATIC_DIRECTORY = Path(__file__).parent / "static"
_QUEUE_MAXIMUM_SIZE = 10
_TIMEOUT_SECONDS = 5.0


def _ntrip_context(
    cfg: NTRIPConfig | None,
    gga_slot: list[GGAData | None],
) -> AbstractContextManager[NTRIPClient | None]:
    if cfg is None:
        return nullcontext()
    return NTRIPClient(cfg, lambda: gga_slot[0])


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    gga_slot: list[GGAData | None] = [None]
    ntrip_cfg = load_ntrip_config()
    loop = asyncio.get_running_loop()
    with (
        ThreadPoolExecutor(max_workers=3) as executor,
        GNSSReader() as gnss,
        IMUReader() as imu,
        _ntrip_context(ntrip_cfg, gga_slot) as ntrip,
    ):
        loop.run_in_executor(executor, run_gnss_loop, loop, gnss, gga_slot)
        loop.run_in_executor(executor, run_imu_loop, loop, imu)
        if ntrip is not None:
            loop.run_in_executor(executor, ntrip.stream)
        yield
        # Interrupt blocking I/O first; executor shutdown(wait=True) follows.
        gnss.cancel()
        imu.cancel()


app = FastAPI(lifespan=_lifespan)


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


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Streams sensor JSON messages to a WebSocket client."""
    await websocket.accept()
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_QUEUE_MAXIMUM_SIZE)
    add_subscriber(queue)

    try:
        await _send_messages_until_disconnect(queue, websocket)
    finally:
        remove_subscriber(queue)


app.mount(
    "/",
    StaticFiles(directory=_STATIC_DIRECTORY, html=True),
    name="static",
)
