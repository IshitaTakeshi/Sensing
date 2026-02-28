"""FastAPI web server for real-time GNSS and IMU sensor visualization.

Start with::

    uvicorn server.main:app --host 0.0.0.0 --port 8000

Then open ``http://<host>:8000/`` in a browser to access the dashboard.
WebSocket clients connect to ``ws://<host>:8000/ws`` and receive a stream
of JSON messages — one ``type="gnss"`` message per GGA sentence (~1 Hz) and
one ``type="imu"`` message every fifth IMU sample (~20 Hz).
"""

import asyncio
import json
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from sensing.gnss import GNSSData, GNSSReader
from sensing.imu import IMUData, IMUReader

_IMU_DECIMATION = 5
_QUEUE_MAX_SIZE = 10
_STATIC_DIR = Path(__file__).parent / "static"
_subscribers: list[asyncio.Queue[str]] = []


def _gnss_to_json(data: GNSSData) -> str:
    vtg = data.vtg
    return json.dumps(
        {
            "type": "gnss",
            "lat": data.gga.latitude_degrees,
            "lon": data.gga.longitude_degrees,
            "alt": data.gga.altitude_meters,
            "fix_quality": data.gga.fix_quality,
            "num_satellites": data.gga.num_satellites,
            "hdop": data.gga.horizontal_dilution_of_precision,
            "utc_time": data.gga.utc_time,
            "speed_ms": vtg.speed_meters_per_second if vtg else None,
            "track_degrees": vtg.track_true_degrees if vtg else None,
            "vtg_valid": vtg.valid if vtg is not None else None,
        }
    )


def _imu_to_json(data: IMUData) -> str:
    return json.dumps(
        {
            "type": "imu",
            "timestamp_ns": data.timestamp_ns,
            "accel_x": data.accel_x,
            "accel_y": data.accel_y,
            "accel_z": data.accel_z,
            "gyro_z": data.gyro_z,
        }
    )


def _enqueue(queue: asyncio.Queue[str], message: str) -> None:
    if queue.full():
        queue.get_nowait()
    queue.put_nowait(message)


def _broadcast(
    message: str,
    subscribers: list[asyncio.Queue[str]],
    loop: asyncio.AbstractEventLoop,
) -> None:
    for queue in list(subscribers):
        loop.call_soon_threadsafe(_enqueue, queue, message)


def _run_gnss_thread(
    subscribers: list[asyncio.Queue[str]],
    loop: asyncio.AbstractEventLoop,
) -> None:
    with GNSSReader() as gnss:
        for data in gnss:
            _broadcast(_gnss_to_json(data), subscribers, loop)


def _try_read_imu(imu: IMUReader) -> IMUData | None:
    try:
        return imu.read()
    except TimeoutError:
        return None


def _run_imu_thread(
    subscribers: list[asyncio.Queue[str]],
    loop: asyncio.AbstractEventLoop,
) -> None:
    counter = 0
    with IMUReader() as imu:
        while True:
            data = _try_read_imu(imu)
            if data is None:
                continue
            counter += 1
            if counter % _IMU_DECIMATION == 0:
                _broadcast(_imu_to_json(data), subscribers, loop)


async def _forward_queue_to_websocket(
    queue: asyncio.Queue[str],
    websocket: WebSocket,
) -> None:
    try:
        while True:
            message = await asyncio.wait_for(queue.get(), timeout=5.0)
            await websocket.send_text(message)
    except TimeoutError:
        await websocket.close(code=1001)
    except WebSocketDisconnect:
        pass


@asynccontextmanager
async def _lifespan(_application: FastAPI) -> AsyncIterator[None]:
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=2)
    loop.run_in_executor(executor, _run_gnss_thread, _subscribers, loop)
    loop.run_in_executor(executor, _run_imu_thread, _subscribers, loop)
    yield
    executor.shutdown(wait=False)


app = FastAPI(lifespan=_lifespan)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Stream GNSS and IMU JSON messages to a connected WebSocket client.

    Each client gets its own bounded queue (max ``_QUEUE_MAX_SIZE`` messages).
    The oldest message is dropped when the queue is full so slow clients do
    not stall the sensor threads. The connection closes — and the client
    should reconnect — if no message arrives within 5 seconds.

    Args:
        websocket: The incoming WebSocket connection.
    """
    await websocket.accept()
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_QUEUE_MAX_SIZE)
    _subscribers.append(queue)
    try:
        await _forward_queue_to_websocket(queue, websocket)
    finally:
        _subscribers.remove(queue)


app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
