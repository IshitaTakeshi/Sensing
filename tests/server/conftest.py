"""Pytest fixtures for server module testing."""

import queue
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from sensing.gnss import GNSSData
from sensing.imu import IMUData


class ControlledGNSSReader:
    def __init__(self) -> None:
        self.message_queue: queue.Queue[GNSSData] = queue.Queue()

    def __enter__(self) -> "ControlledGNSSReader":
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def __iter__(self) -> Iterator[GNSSData]:
        while True:
            try:
                yield self.message_queue.get(timeout=0.05)
            except queue.Empty:
                return


class ControlledIMUReader:
    def __init__(self) -> None:
        self.message_queue: queue.Queue[IMUData] = queue.Queue()

    def __enter__(self) -> "ControlledIMUReader":
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def read(self, timeout: float = 0.01) -> IMUData:
        try:
            return self.message_queue.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError() from exc


@pytest.fixture(autouse=True)
def mock_hardware_readers() -> (
    Iterator[tuple[ControlledGNSSReader, ControlledIMUReader]]
):
    gnss_controller = ControlledGNSSReader()
    imu_controller = ControlledIMUReader()
    with (
        patch("server.sensors.GNSSReader", return_value=gnss_controller),
        patch("server.sensors.IMUReader", return_value=imu_controller),
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
