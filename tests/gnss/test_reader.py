"""Tests for the GNSS serial reader module."""

import itertools
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import serial

from sensing.gnss import GNSSData, GNSSReader
from sensing.nmea.types import GGAData, VTGData

# ---------------------------------------------------------------------------
# Valid NMEA sentence constants
# ---------------------------------------------------------------------------

# RTK Fixed, 12 satellites — from sensing.nmea.types docstring
_GGA_RTK = "$GNGGA,123519.00,4807.038,N,01131.000,E,4,12,0.5,545.4,M,47.0,M,,*7D"

# Standard GPS fix
_GGA_SPS = "$GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*7F"

# No fix (fix_quality=0)
_GGA_NO_FIX = "$GNGGA,123519.00,,,,,,0,00,99.9,,M,,M,,*60"

# Differential mode — from sensing.nmea.vtg docstring
_VTG_DIFF = "$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,D*3E"

# Autonomous mode — from sensing.nmea.vtg module
_VTG_AUTO = "$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,A*3B"

# An unrelated sentence type (GSA) that both parsers must silently skip
_GSA = "$GNGSA,A,3,01,02,03,04,05,06,07,08,09,10,11,12,1.0,0.5,0.9*27"

# An obviously malformed line
_GARBAGE = "not-nmea-at-all"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _encode(lines: list[str]) -> list[bytes]:
    """Convert sentence strings to ASCII bytes as serial.readline() returns."""
    return [line.encode("ascii") for line in lines]


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_hw(monkeypatch):
    """Replace serial.Serial with a mock for the duration of a test.

    Returns a SimpleNamespace with attributes:
        ser      -- the Serial instance mock
        ser_cls  -- the Serial class mock (to verify constructor call args)

    Configure ``ser.readline.side_effect`` with a list of byte strings to
    control what the reader sees, followed by ``b""`` to simulate EOF/timeout.
    """
    mock_ser = MagicMock()
    mock_ser_cls = MagicMock(return_value=mock_ser)
    monkeypatch.setattr(serial, "Serial", mock_ser_cls)

    return SimpleNamespace(ser=mock_ser, ser_cls=mock_ser_cls)


# ---------------------------------------------------------------------------
# GNSSData type
# ---------------------------------------------------------------------------


class TestGNSSData:
    def test_holds_gga_and_vtg(self):
        gga = MagicMock(spec=GGAData)
        vtg = MagicMock(spec=VTGData)
        data = GNSSData(gga=gga, vtg=vtg)
        assert data.gga is gga
        assert data.vtg is vtg

    def test_vtg_defaults_to_none(self):
        gga = MagicMock(spec=GGAData)
        data = GNSSData(gga=gga)
        assert data.vtg is None


# ---------------------------------------------------------------------------
# GNSSReader — error conditions (no hardware needed)
# ---------------------------------------------------------------------------


class TestGNSSReaderErrors:
    def test_read_raises_runtime_error_outside_context(self):
        with pytest.raises(RuntimeError, match="context manager"):
            GNSSReader().read()


# ---------------------------------------------------------------------------
# GNSSReader — setup
# ---------------------------------------------------------------------------


class TestGNSSReaderSetup:
    def test_opens_serial_with_correct_port(self, mock_hw):
        mock_hw.ser.readline.side_effect = _encode([_GGA_SPS]) + [b""] * 100
        with GNSSReader(port="/dev/ttyAMA5") as gnss:
            gnss.read()
        mock_hw.ser_cls.assert_called_once()
        assert mock_hw.ser_cls.call_args.args[0] == "/dev/ttyAMA5"

    def test_opens_serial_with_correct_baudrate(self, mock_hw):
        mock_hw.ser.readline.side_effect = _encode([_GGA_SPS]) + [b""] * 100
        with GNSSReader(baudrate=38400) as gnss:
            gnss.read()
        assert mock_hw.ser_cls.call_args.kwargs["baudrate"] == 38400

    def test_custom_port_and_baudrate_are_forwarded(self, mock_hw):
        mock_hw.ser.readline.side_effect = _encode([_GGA_SPS]) + [b""] * 100
        with GNSSReader(port="/dev/ttyUSB0", baudrate=9600) as gnss:
            gnss.read()
        assert mock_hw.ser_cls.call_args.args[0] == "/dev/ttyUSB0"
        assert mock_hw.ser_cls.call_args.kwargs["baudrate"] == 9600


# ---------------------------------------------------------------------------
# GNSSReader — read()
# ---------------------------------------------------------------------------


class TestGNSSReaderRead:
    def test_returns_gnss_data_instance(self, mock_hw):
        mock_hw.ser.readline.side_effect = _encode([_GGA_SPS]) + [b""] * 100
        with GNSSReader() as gnss:
            data = gnss.read()
        assert isinstance(data, GNSSData)

    def test_vtg_is_none_before_any_vtg_received(self, mock_hw):
        mock_hw.ser.readline.side_effect = _encode([_GGA_SPS]) + [b""] * 100
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.vtg is None

    def test_vtg_paired_with_preceding_vtg(self, mock_hw):
        mock_hw.ser.readline.side_effect = _encode([_VTG_DIFF, _GGA_SPS]) + [b""] * 100
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.vtg is not None
        assert data.vtg.mode == "D"

    def test_most_recent_vtg_is_used(self, mock_hw):
        # Two VTG sentences before one GGA: only the last VTG should be paired.
        mock_hw.ser.readline.side_effect = _encode(
            [_VTG_AUTO, _VTG_DIFF, _GGA_SPS]
        ) + [b""] * 100
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.vtg is not None
        assert data.vtg.mode == "D"

    def test_gga_fields_are_correctly_parsed(self, mock_hw):
        mock_hw.ser.readline.side_effect = _encode([_GGA_RTK]) + [b""] * 100
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.gga.fix_quality == 4
        assert data.gga.latitude_degrees == pytest.approx(48.1173, rel=1e-4)
        assert data.gga.longitude_degrees == pytest.approx(11.5167, rel=1e-4)
        assert data.gga.valid is True

    def test_no_fix_gga_is_returned_with_valid_false(self, mock_hw):
        mock_hw.ser.readline.side_effect = _encode([_GGA_NO_FIX]) + [b""] * 100
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.gga.valid is False
        assert data.gga.fix_quality == 0

    def test_non_gga_non_vtg_lines_are_skipped(self, mock_hw):
        mock_hw.ser.readline.side_effect = _encode(
            [_GSA, _GARBAGE, _GGA_SPS]
        ) + [b""] * 100
        with GNSSReader() as gnss:
            data = gnss.read()
        assert isinstance(data, GNSSData)
        assert data.gga.fix_quality == 1

    def test_vtg_state_persists_across_multiple_reads(self, mock_hw):
        # VTG received before first GGA, then a second GGA with no intervening VTG.
        mock_hw.ser.readline.side_effect = _encode(
            [_VTG_DIFF, _GGA_SPS, _GGA_RTK]
        ) + [b""] * 100
        with GNSSReader() as gnss:
            first = gnss.read()
            second = gnss.read()
        assert first.vtg is not None
        assert first.vtg.mode == "D"
        # Second read: no new VTG, so the same last_vtg is reused.
        assert second.vtg is not None
        assert second.vtg.mode == "D"


# ---------------------------------------------------------------------------
# GNSSReader — cleanup
# ---------------------------------------------------------------------------


class TestGNSSReaderCleanup:
    def test_closes_serial_on_normal_exit(self, mock_hw):
        mock_hw.ser.readline.side_effect = _encode([_GGA_SPS]) + [b""] * 100
        with GNSSReader() as gnss:
            gnss.read()
        mock_hw.ser.close.assert_called_once()

    def test_closes_serial_on_exception(self, mock_hw):
        with pytest.raises(ValueError, match="test"), GNSSReader():
            raise ValueError("test")
        mock_hw.ser.close.assert_called_once()


# ---------------------------------------------------------------------------
# GNSSReader — __iter__
# ---------------------------------------------------------------------------


class TestGNSSReaderIter:
    def test_yields_gnss_data_instances(self, mock_hw):
        sentences = [_VTG_DIFF, _GGA_SPS, _GGA_RTK, _GGA_NO_FIX]
        mock_hw.ser.readline.side_effect = _encode(sentences) + [b""] * 100
        with GNSSReader() as gnss:
            samples = list(itertools.islice(gnss, 3))
        assert len(samples) == 3
        assert all(isinstance(s, GNSSData) for s in samples)

    def test_iter_yields_vtg_from_first_read(self, mock_hw):
        sentences = [_VTG_AUTO, _GGA_SPS, _GGA_RTK]
        mock_hw.ser.readline.side_effect = _encode(sentences) + [b""] * 100
        with GNSSReader() as gnss:
            samples = list(itertools.islice(gnss, 2))
        assert samples[0].vtg is not None
        assert samples[0].vtg.mode == "A"
