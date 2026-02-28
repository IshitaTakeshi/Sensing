"""Pytest fixtures for server module testing."""

import queue
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from sensing.gnss import GNSSData
from sensing.imu import IMUData


class ControlledGNSSReader:
    def __init__(self) -> None:
        self.message_queue: queue.Queue[GNSSData | None] = queue.Queue()

    def __enter__(self) -> "ControlledGNSSReader":
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def cancel(self) -> None:
        """Unblocks the queue wait instantly."""
        self.message_queue.put(None)

    def __iter__(self) -> Iterator[GNSSData]:
        while True:
            # Safe, blocking wait. No fragile CI timeout needed.
            data = self.message_queue.get()
            if data is None:
                return
            yield data


class ControlledIMUReader:
    def __init__(self) -> None:
        self.message_queue: queue.Queue[IMUData | None] = queue.Queue()

    def __enter__(self) -> "ControlledIMUReader":
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def cancel(self) -> None:
        """Trigger an OSError simulation on next read."""
        self.message_queue.put(None)

    def read(self, timeout: float = 0.01) -> IMUData:
        try:
            data = self.message_queue.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError() from exc

        if data is None:
            raise OSError("Simulated hardware disconnect.")

        return data


@pytest.fixture(autouse=True)
def mock_hardware_readers() -> (
    Iterator[tuple[ControlledGNSSReader, ControlledIMUReader]]
):
    gnss_controller = ControlledGNSSReader()
    imu_controller = ControlledIMUReader()
    with (
        patch("server.main.GNSSReader", return_value=gnss_controller),
        patch("server.main.IMUReader", return_value=imu_controller),
    ):
        yield gnss_controller, imu_controller


@pytest.fixture
def gnss_controller(
    mock_hardware_readers: tuple[ControlledGNSSReader, ControlledIMUReader],
) -> ControlledGNSSReader:
    return mock_hardware_readers[0]


@pytest.fixture
def imu_controller(
    mock_hardware_readers: tuple[ControlledGNSSReader, ControlledIMUReader],
) -> ControlledIMUReader:
    return mock_hardware_readers[1]
