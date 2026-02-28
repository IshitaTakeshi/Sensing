"""Tests for the ISM330DHCX IMU reader module."""

import itertools
import math
import struct
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import gpiod
import pytest
import spidev
from gpiod.line import Clock, Direction, Edge

from sensing.imu import IMUData, IMUReader
from sensing.imu.reader import (
    _ACCEL_SENSITIVITY,
    _GYRO_SENSITIVITY,
    _REG_CTRL1_XL,
    _REG_CTRL2_G,
    _REG_CTRL3_C,
    _REG_INT1_CTRL,
    _REG_OUTX_L_G,
    _parse_sample,
    _read_sample,
    _reset_imu,
    _start_imu,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_raw(
    gx: int = 0,
    gy: int = 0,
    gz: int = 0,
    ax: int = 0,
    ay: int = 0,
    az: int = 0,
) -> bytes:
    """Pack six signed 16-bit integers into 12 raw output-register bytes."""
    return struct.pack("<hhhhhh", gx, gy, gz, ax, ay, az)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_hw(monkeypatch):
    """Replace all hardware objects with mocks for the duration of a test.

    Patches spidev.SpiDev, gpiod.Chip, and time.sleep so that IMUReader can
    be instantiated and exercised without hardware.

    Returns a SimpleNamespace with attributes:
        spi       -- the SpiDev instance mock
        chip      -- the Chip instance mock
        chip_cls  -- the Chip class mock (to verify constructor call args)
        request   -- the LineRequest mock
        event     -- the mock edge event (to control timestamp_ns)
    """
    mock_spi = MagicMock()
    mock_spi.xfer2.return_value = [0] * 13

    mock_event = MagicMock()
    mock_event.timestamp_ns = 0

    mock_request = MagicMock()
    mock_request.wait_edge_events.return_value = True
    mock_request.read_edge_events.return_value = [mock_event]

    mock_chip = MagicMock()
    mock_chip.request_lines.return_value = mock_request

    mock_chip_cls = MagicMock(return_value=mock_chip)

    monkeypatch.setattr(spidev, "SpiDev", MagicMock(return_value=mock_spi))
    monkeypatch.setattr(gpiod, "Chip", mock_chip_cls)
    monkeypatch.setattr(time, "sleep", MagicMock())

    return SimpleNamespace(
        spi=mock_spi,
        chip=mock_chip,
        chip_cls=mock_chip_cls,
        request=mock_request,
        event=mock_event,
    )


# ---------------------------------------------------------------------------
# _parse_sample
# ---------------------------------------------------------------------------


class TestParseSample:
    """Tests for the pure byte-to-physical-unit conversion function."""

    def test_all_zeros_produce_zero_output(self):
        sample = _parse_sample(_make_raw(), timestamp_ns=0)
        assert sample.accel_x == pytest.approx(0.0)
        assert sample.accel_y == pytest.approx(0.0)
        assert sample.accel_z == pytest.approx(0.0)
        assert sample.gyro_x == pytest.approx(0.0)
        assert sample.gyro_y == pytest.approx(0.0)
        assert sample.gyro_z == pytest.approx(0.0)

    def test_one_lsb_accel_x(self):
        sample = _parse_sample(_make_raw(ax=1), timestamp_ns=0)
        assert sample.accel_x == pytest.approx(_ACCEL_SENSITIVITY)
        assert sample.accel_y == pytest.approx(0.0)
        assert sample.accel_z == pytest.approx(0.0)

    def test_one_lsb_accel_y(self):
        sample = _parse_sample(_make_raw(ay=1), timestamp_ns=0)
        assert sample.accel_x == pytest.approx(0.0)
        assert sample.accel_y == pytest.approx(_ACCEL_SENSITIVITY)
        assert sample.accel_z == pytest.approx(0.0)

    def test_one_lsb_accel_z(self):
        sample = _parse_sample(_make_raw(az=1), timestamp_ns=0)
        assert sample.accel_x == pytest.approx(0.0)
        assert sample.accel_z == pytest.approx(_ACCEL_SENSITIVITY)

    def test_one_lsb_gyro_x(self):
        sample = _parse_sample(_make_raw(gx=1), timestamp_ns=0)
        assert sample.gyro_x == pytest.approx(_GYRO_SENSITIVITY)
        assert sample.gyro_y == pytest.approx(0.0)
        assert sample.gyro_z == pytest.approx(0.0)

    def test_one_lsb_gyro_y(self):
        sample = _parse_sample(_make_raw(gy=1), timestamp_ns=0)
        assert sample.gyro_x == pytest.approx(0.0)
        assert sample.gyro_y == pytest.approx(_GYRO_SENSITIVITY)
        assert sample.gyro_z == pytest.approx(0.0)

    def test_one_lsb_gyro_z(self):
        sample = _parse_sample(_make_raw(gz=1), timestamp_ns=0)
        assert sample.gyro_z == pytest.approx(_GYRO_SENSITIVITY)

    def test_negative_accel(self):
        sample = _parse_sample(_make_raw(ax=-1), timestamp_ns=0)
        assert sample.accel_x == pytest.approx(-_ACCEL_SENSITIVITY)

    def test_negative_gyro(self):
        sample = _parse_sample(_make_raw(gx=-1), timestamp_ns=0)
        assert sample.gyro_x == pytest.approx(-_GYRO_SENSITIVITY)

    def test_max_int16(self):
        sample = _parse_sample(_make_raw(ax=32767, gx=32767), timestamp_ns=0)
        assert sample.accel_x == pytest.approx(32767 * _ACCEL_SENSITIVITY)
        assert sample.gyro_x == pytest.approx(32767 * _GYRO_SENSITIVITY)

    def test_min_int16(self):
        sample = _parse_sample(_make_raw(ax=-32768, gx=-32768), timestamp_ns=0)
        assert sample.accel_x == pytest.approx(-32768 * _ACCEL_SENSITIVITY)
        assert sample.gyro_x == pytest.approx(-32768 * _GYRO_SENSITIVITY)

    def test_approx_one_g_on_z_axis(self):
        # 16384 LSB * 0.061 mg/LSB ≈ 999 mg; rel=1e-2 allows for LSB rounding
        sample = _parse_sample(_make_raw(az=16384), timestamp_ns=0)
        assert sample.accel_z == pytest.approx(9.80665, rel=1e-2)

    def test_full_scale_gyro_is_2293_dps_not_2000(self):
        # The FS=±2000 dps label is not the true full-scale range.
        # Datasheet sensitivity: 70 mdps/LSB (TYP), so max int16 (32767 LSB)
        # gives 32767 * 70e-3 = 2293.69 dps, not 2000 dps.
        sample = _parse_sample(_make_raw(gz=32767), timestamp_ns=0)
        expected_rad_s = 2293.69 * (math.pi / 180.0)
        assert sample.gyro_z == pytest.approx(expected_rad_s, rel=1e-3)

    def test_timestamp_is_preserved(self):
        ts = 1_700_000_000_123_456_789
        sample = _parse_sample(_make_raw(), timestamp_ns=ts)
        assert sample.timestamp_ns == ts

    def test_all_six_axes_are_independent(self):
        sample = _parse_sample(_make_raw(gx=1, gy=2, gz=3, ax=4, ay=5, az=6), timestamp_ns=0)
        assert sample.gyro_x == pytest.approx(1 * _GYRO_SENSITIVITY)
        assert sample.gyro_y == pytest.approx(2 * _GYRO_SENSITIVITY)
        assert sample.gyro_z == pytest.approx(3 * _GYRO_SENSITIVITY)
        assert sample.accel_x == pytest.approx(4 * _ACCEL_SENSITIVITY)
        assert sample.accel_y == pytest.approx(5 * _ACCEL_SENSITIVITY)
        assert sample.accel_z == pytest.approx(6 * _ACCEL_SENSITIVITY)

    def test_returns_imu_data_instance(self):
        sample = _parse_sample(_make_raw(), timestamp_ns=0)
        assert isinstance(sample, IMUData)


# ---------------------------------------------------------------------------
# _reset_imu
# ---------------------------------------------------------------------------


class TestResetImu:
    """Tests for the IMU software-reset sequence."""

    def test_first_write_is_sw_reset(self):
        spi = MagicMock()
        _reset_imu(spi)
        assert spi.xfer2.call_args_list[0] == call([_REG_CTRL3_C, 0x01])

    def test_second_write_enables_bdu_and_ifinc(self):
        spi = MagicMock()
        _reset_imu(spi)
        assert spi.xfer2.call_args_list[1] == call([_REG_CTRL3_C, 0x44])

    def test_exactly_two_spi_writes(self):
        spi = MagicMock()
        _reset_imu(spi)
        assert spi.xfer2.call_count == 2


# ---------------------------------------------------------------------------
# _start_imu
# ---------------------------------------------------------------------------


class TestStartImu:
    """Tests for the IMU measurement-start sequence."""

    def test_exactly_three_spi_writes(self):
        spi = MagicMock()
        _start_imu(spi)
        assert spi.xfer2.call_count == 3

    def test_enables_drdy_interrupt_on_int1(self):
        spi = MagicMock()
        _start_imu(spi)
        assert call([_REG_INT1_CTRL, 0x01]) in spi.xfer2.call_args_list

    def test_configures_gyroscope(self):
        spi = MagicMock()
        _start_imu(spi)
        assert call([_REG_CTRL2_G, 0x4C]) in spi.xfer2.call_args_list

    def test_configures_accelerometer(self):
        spi = MagicMock()
        _start_imu(spi)
        assert call([_REG_CTRL1_XL, 0x40]) in spi.xfer2.call_args_list

    def test_accel_is_written_last_to_start_cycle(self):
        # CTRL1_XL triggers the shared measurement cycle, so it must come last.
        spi = MagicMock()
        _start_imu(spi)
        assert spi.xfer2.call_args_list[-1] == call([_REG_CTRL1_XL, 0x40])


# ---------------------------------------------------------------------------
# _read_sample
# ---------------------------------------------------------------------------


class TestReadSample:
    """Tests for the SPI burst-read wrapper."""

    def test_sends_read_bit_on_register_address(self):
        spi = MagicMock()
        spi.xfer2.return_value = [0] * 13
        _read_sample(spi, timestamp_ns=0)
        cmd = spi.xfer2.call_args[0][0]
        assert cmd[0] == _REG_OUTX_L_G | 0x80

    def test_sends_thirteen_byte_message(self):
        spi = MagicMock()
        spi.xfer2.return_value = [0] * 13
        _read_sample(spi, timestamp_ns=0)
        assert len(spi.xfer2.call_args[0][0]) == 13

    def test_parses_spi_response_into_imu_data(self):
        spi = MagicMock()
        raw = _make_raw(gx=10, ax=20)
        spi.xfer2.return_value = [0, *list(raw)]
        sample = _read_sample(spi, timestamp_ns=0)
        assert sample.gyro_x == pytest.approx(10 * _GYRO_SENSITIVITY)
        assert sample.accel_x == pytest.approx(20 * _ACCEL_SENSITIVITY)


# ---------------------------------------------------------------------------
# IMUReader
# ---------------------------------------------------------------------------


class TestIMUReaderErrors:
    """Tests for IMUReader error conditions that need no hardware mock."""

    def test_read_raises_runtime_error_outside_context(self):
        with pytest.raises(RuntimeError, match="context manager"):
            IMUReader().read()


class TestIMUReaderSetup:
    """Tests for IMUReader hardware initialisation."""

    def test_opens_spi_with_correct_bus_and_device(self, mock_hw):
        with IMUReader(spi_bus=0, spi_device=1):
            mock_hw.spi.open.assert_called_once_with(0, 1)

    def test_sets_spi_speed_and_mode(self, mock_hw):
        with IMUReader():
            assert mock_hw.spi.max_speed_hz == 5_000_000
            assert mock_hw.spi.mode == 0

    def test_requests_correct_gpio_chip(self, mock_hw):
        with IMUReader(gpio_chip="/dev/gpiochip4"):
            mock_hw.chip_cls.assert_called_once_with("/dev/gpiochip4")

    def test_requests_gpio_line_with_rising_edge(self, mock_hw):
        with IMUReader(gpio_line=25):
            config = mock_hw.chip.request_lines.call_args.kwargs["config"]
            settings = config[25]
            assert settings.direction == Direction.INPUT
            assert settings.edge_detection == Edge.RISING
            assert settings.event_clock == Clock.REALTIME

    def test_requests_gpio_with_consumer_name(self, mock_hw):
        with IMUReader():
            consumer = mock_hw.chip.request_lines.call_args.kwargs["consumer"]
            assert consumer == "IMUReader"

    def test_reset_is_called_before_gpio_setup(self, mock_hw):
        # _reset_imu writes to SPI; GPIO request_lines must happen after.
        call_order = []
        mock_hw.spi.xfer2.side_effect = lambda _: call_order.append("spi") or [0] * 13
        mock_hw.chip.request_lines.side_effect = lambda **_: (
            call_order.append("gpio") or mock_hw.request
        )
        with IMUReader():
            pass
        assert call_order.index("spi") < call_order.index("gpio")


class TestIMUReaderRead:
    """Tests for IMUReader.read()."""

    def test_raises_timeout_error_when_no_interrupt(self, mock_hw):
        mock_hw.request.wait_edge_events.return_value = False
        with pytest.raises(TimeoutError, match="DRDY"), IMUReader() as imu:
            imu.read(timeout=0.1)

    def test_consumes_interrupt_before_sampling(self, mock_hw):
        with IMUReader() as imu:
            imu.read()
        mock_hw.request.read_edge_events.assert_called()

    def test_returns_imu_data_instance(self, mock_hw):
        with IMUReader() as imu:
            sample = imu.read()
        assert isinstance(sample, IMUData)
        assert mock_hw.request.read_edge_events.called

    def test_timestamp_comes_from_kernel_edge_event(self, mock_hw):
        mock_hw.event.timestamp_ns = 1_700_000_000_500_000_000
        with IMUReader() as imu:
            sample = imu.read()
        assert sample.timestamp_ns == 1_700_000_000_500_000_000


class TestIMUReaderCleanup:
    """Tests for IMUReader resource release."""

    def test_releases_gpio_line_on_exit(self, mock_hw):
        with IMUReader():
            pass
        mock_hw.request.release.assert_called_once()

    def test_closes_gpio_chip_on_exit(self, mock_hw):
        with IMUReader():
            pass
        mock_hw.chip.close.assert_called_once()

    def test_closes_spi_on_exit(self, mock_hw):
        with IMUReader():
            pass
        mock_hw.spi.close.assert_called_once()

    def test_releases_resources_when_exception_raised(self, mock_hw):
        with pytest.raises(ValueError, match="test"), IMUReader():
            raise ValueError("test")
        mock_hw.request.release.assert_called_once()
        mock_hw.spi.close.assert_called_once()


class TestIMUReaderIter:
    """Tests for IMUReader.__iter__."""

    def test_yields_imu_data_instances(self, mock_hw):
        with IMUReader() as imu:
            samples = list(itertools.islice(imu, 3))
        assert len(samples) == 3
        assert mock_hw.request.read_edge_events.call_count == 3

    def test_stops_on_timeout_error(self, mock_hw):
        mock_hw.request.wait_edge_events.side_effect = [True, True, False]
        with pytest.raises(TimeoutError), IMUReader() as imu:
            for _ in imu:
                pass
