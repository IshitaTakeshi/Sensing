"""Background sensor reading loops."""

import asyncio
import threading

from sensing.gnss import GNSSReader
from sensing.imu import IMUData, IMUReader
from server.broadcaster import broadcast_message
from server.formatters import format_gnss_message, format_imu_message

__all__ = ["run_gnss_loop", "run_imu_loop"]

_IMU_DECIMATION = 5


def run_gnss_loop(loop: asyncio.AbstractEventLoop, stop: threading.Event) -> None:
    """Read GNSS data continuously and broadcast it to the event loop."""
    with GNSSReader() as gnss:
        for data in gnss:
            if stop.is_set():
                break
            broadcast_message(format_gnss_message(data), loop)


def _read_imu_safely(imu: IMUReader) -> IMUData | None:
    try:
        return imu.read()
    except TimeoutError:
        return None


def _process_imu_reading(
    imu: IMUReader, loop: asyncio.AbstractEventLoop, counter: int
) -> int:
    data = _read_imu_safely(imu)
    if data is None:
        return counter

    if counter % _IMU_DECIMATION == 0:
        message = format_imu_message(data)
        broadcast_message(message, loop)

    return counter + 1


def run_imu_loop(loop: asyncio.AbstractEventLoop, stop: threading.Event) -> None:
    """Read IMU data continuously, decimate it, and broadcast."""
    counter = 0
    with IMUReader() as imu:
        while not stop.is_set():
            counter = _process_imu_reading(imu, loop, counter)
