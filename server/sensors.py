"""Background sensor reading loops."""

import asyncio

from sensing.gnss import GNSSReader
from sensing.imu import IMUData, IMUReader
from server.broadcaster import broadcast_message
from server.formatters import format_gnss_message, format_imu_message

__all__ = ["run_gnss_loop", "run_imu_loop"]

_IMU_DECIMATION = 5


def run_gnss_loop(loop: asyncio.AbstractEventLoop, gnss: GNSSReader) -> None:
    """Read GNSS data continuously and broadcast it to the event loop.

    The caller owns *gnss* and must use it as an open context manager. The
    loop exits when ``gnss.cancel()`` is called, which causes the underlying
    ``GNSSReader.read()`` to raise ``EOFError``.

    Args:
        loop: Running asyncio event loop to broadcast messages on.
        gnss: An open ``GNSSReader`` instance managed by the caller.
    """
    try:
        for data in gnss:
            message = format_gnss_message(data)
            broadcast_message(message, loop)
    except EOFError:
        return


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


def run_imu_loop(loop: asyncio.AbstractEventLoop, imu: IMUReader) -> None:
    """Read IMU data continuously, decimate it, and broadcast.

    The caller owns *imu* and must use it as an open context manager. The
    loop exits when ``imu.cancel()`` is called, which causes the underlying
    ``IMUReader.read()`` to raise ``OSError``.

    Args:
        loop: Running asyncio event loop to broadcast messages on.
        imu: An open ``IMUReader`` instance managed by the caller.
    """
    counter = 0
    try:
        while True:
            counter = _process_imu_reading(imu, loop, counter)
    except OSError:
        return
