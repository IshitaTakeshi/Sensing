"""Tests for the GNSS gpsd client reader module."""

import contextlib
import itertools
import json
import socket
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from sensing.gnss import GNSSData, GNSSReader
from sensing.nmea.types import GGAData, VTGData

# ---------------------------------------------------------------------------
# gpsd JSON message dictionaries
# ---------------------------------------------------------------------------

# RTK Fixed fix, with speed and track
_TPV_RTK = {
    "class": "TPV",
    "status": 3,
    "time": "2025-03-01T12:35:19.000Z",
    "lat": 48.1173,
    "lon": 11.5167,
    "altMSL": 545.4,
    "speed": 2.833,
    "track": 54.7,
}

# Standard GPS fix
_TPV_SPS = {
    "class": "TPV",
    "status": 1,
    "time": "2025-03-01T12:35:19.000Z",
    "lat": 48.1173,
    "lon": 11.5167,
    "altMSL": 545.4,
    "speed": 2.833,
    "track": 54.7,
}

# DGPS fix
_TPV_DGPS = {
    "class": "TPV",
    "status": 2,
    "lat": 48.1173,
    "lon": 11.5167,
    "altMSL": 545.4,
    "speed": 1.5,
    "track": 90.0,
}

# No fix -- no position or velocity fields
_TPV_NO_FIX = {
    "class": "TPV",
    "status": 0,
}

# SKY message with 12 used satellites and good HDOP
_SKY_12 = {
    "class": "SKY",
    "uSat": 12,
    "hdop": 0.5,
}

# SKY message where only nSat is present (older gpsd without uSat, no satellites list)
_SKY_NSAT_ONLY = {
    "class": "SKY",
    "nSat": 8,
    "hdop": 1.2,
}

# SKY without uSat but with per-satellite used flags (3 out of 4 used)
_SKY_SATELLITES_WITH_FLAGS = {
    "class": "SKY",
    "nSat": 10,
    "hdop": 0.7,
    "satellites": [
        {"PRN": 1, "used": True},
        {"PRN": 2, "used": True},
        {"PRN": 3, "used": False},
        {"PRN": 4, "used": True},
    ],
}

# SKY with satellites list but no per-satellite used field (fall back to nSat)
_SKY_SATELLITES_NO_USED_FLAG = {
    "class": "SKY",
    "nSat": 5,
    "hdop": 1.0,
    "satellites": [
        {"PRN": 1, "el": 45},
        {"PRN": 2, "el": 30},
    ],
}

# A gpsd WATCH echo -- should be silently ignored
_WATCH_MSG = {"class": "WATCH", "enable": True}

# A gpsd VERSION message -- should be silently ignored
_VERSION_MSG = {"class": "VERSION", "release": "3.25"}

# An obviously malformed line
_GARBAGE = "not-json-at-all"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _line(msg: dict) -> bytes:
    """Encode a dict as a newline-terminated JSON line."""
    return (json.dumps(msg) + "\n").encode()


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_gpsd(monkeypatch):
    """Replace socket.create_connection with a mock for the duration of a test.

    Returns a SimpleNamespace with attributes:
        sock     -- the socket instance mock
        stream   -- the stream mock returned by sock.makefile()
        connect  -- the create_connection mock (to verify call args)

    Configure ``stream.readline.side_effect`` with a list of byte strings
    to control what the reader sees.  A trailing ``OSError`` simulates a
    closed connection; omit it when the test reads only a fixed number of
    messages and will not exhaust the list.
    """
    mock_stream = MagicMock()
    mock_sock = MagicMock()
    mock_sock.makefile.return_value = mock_stream
    mock_connect = MagicMock(return_value=mock_sock)
    monkeypatch.setattr(socket, "create_connection", mock_connect)
    return SimpleNamespace(sock=mock_sock, stream=mock_stream, connect=mock_connect)


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
# GNSSReader -- error conditions (no hardware needed)
# ---------------------------------------------------------------------------


class TestGNSSReaderErrors:
    def test_read_raises_runtime_error_outside_context(self):
        with pytest.raises(RuntimeError, match="context manager"):
            GNSSReader().read()


# ---------------------------------------------------------------------------
# GNSSReader -- connection setup
# ---------------------------------------------------------------------------


class TestGNSSReaderSetup:
    def test_connects_to_default_host_and_port(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_TPV_SPS)]
        with GNSSReader() as gnss:
            gnss.read()
        mock_gpsd.connect.assert_called_once_with(("localhost", 2947))

    def test_sends_watch_command_on_enter(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_TPV_SPS)]
        with GNSSReader() as gnss:
            gnss.read()
        mock_gpsd.sock.sendall.assert_called_once_with(
            b'?WATCH={"enable":true,"json":true}\n'
        )

    def test_custom_host_and_port_are_forwarded(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_TPV_SPS)]
        with GNSSReader(host="192.168.1.10", port=2948) as gnss:
            gnss.read()
        mock_gpsd.connect.assert_called_once_with(("192.168.1.10", 2948))

    def test_socket_timeout_is_set_on_enter(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_TPV_SPS)]
        with GNSSReader() as gnss:
            gnss.read()
        mock_gpsd.sock.settimeout.assert_called_once()

    def test_socket_closed_if_sendall_raises_on_enter(self, mock_gpsd):
        mock_gpsd.sock.sendall.side_effect = OSError("refused")
        with pytest.raises(OSError):
            with GNSSReader():
                pass
        mock_gpsd.sock.close.assert_called_once()


# ---------------------------------------------------------------------------
# GNSSReader - read
# ---------------------------------------------------------------------------


class TestGNSSReaderRead:
    def test_returns_gnss_data_instance(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_TPV_SPS)]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert isinstance(data, GNSSData)

    def test_gga_fields_from_rtk_tpv(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_TPV_RTK)]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.gga.fix_quality == 4  # status 3 -> fix_quality 4
        assert data.gga.latitude_degrees == pytest.approx(48.1173, rel=1e-4)
        assert data.gga.longitude_degrees == pytest.approx(11.5167, rel=1e-4)
        assert data.gga.altitude_meters == pytest.approx(545.4, rel=1e-4)
        assert data.gga.valid is True

    def test_no_fix_tpv_gives_valid_false(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_TPV_NO_FIX)]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.gga.valid is False
        assert data.gga.fix_quality == 0

    def test_utc_time_converted_from_iso8601(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_TPV_SPS)]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.gga.utc_time == "123519.00"

    def test_utc_time_none_when_absent_from_tpv(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_TPV_NO_FIX)]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.gga.utc_time is None

    def test_altmsl_used_for_altitude(self, mock_gpsd):
        tpv = {**_TPV_SPS, "altMSL": 100.0, "alt": 150.0}
        mock_gpsd.stream.readline.side_effect = [_line(tpv)]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.gga.altitude_meters == pytest.approx(100.0)

    def test_alt_fallback_when_altmsl_absent(self, mock_gpsd):
        tpv = {k: v for k, v in _TPV_SPS.items() if k != "altMSL"}
        tpv["alt"] = 150.0
        mock_gpsd.stream.readline.side_effect = [_line(tpv)]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.gga.altitude_meters == pytest.approx(150.0)

    def test_sky_fields_applied_to_subsequent_tpv(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_SKY_12), _line(_TPV_SPS)]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.gga.num_satellites == 12
        assert data.gga.horizontal_dilution_of_precision == pytest.approx(0.5)

    def test_sky_nsat_fallback_when_usat_absent(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [
            _line(_SKY_NSAT_ONLY),
            _line(_TPV_SPS),
        ]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.gga.num_satellites == 8

    def test_sky_satellites_used_flags_derived_when_usat_absent(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [
            _line(_SKY_SATELLITES_WITH_FLAGS),
            _line(_TPV_SPS),
        ]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.gga.num_satellites == 3  # 3 of 4 entries have used=True

    def test_sky_falls_back_to_nsat_when_no_used_flag_in_satellites(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [
            _line(_SKY_SATELLITES_NO_USED_FLAG),
            _line(_TPV_SPS),
        ]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.gga.num_satellites == 5  # falls back to nSat

    def test_sky_nsat_non_int_returns_none(self, mock_gpsd):
        sky = {**_SKY_NSAT_ONLY, "nSat": "bad"}
        mock_gpsd.stream.readline.side_effect = [_line(sky), _line(_TPV_SPS)]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.gga.num_satellites is None

    def test_satellite_count_none_when_no_sky_received(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_TPV_SPS)]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.gga.num_satellites is None
        assert data.gga.horizontal_dilution_of_precision is None

    def test_sky_state_persists_across_tpv_messages(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [
            _line(_SKY_12),
            _line(_TPV_SPS),
            _line(_TPV_RTK),
        ]
        with GNSSReader() as gnss:
            first = gnss.read()
            second = gnss.read()
        assert first.gga.num_satellites == 12
        assert second.gga.num_satellites == 12

    def test_vtg_speed_and_track_from_tpv(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_TPV_SPS)]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.vtg is not None
        assert data.vtg.speed_meters_per_second == pytest.approx(2.833, rel=1e-4)
        assert data.vtg.track_true_degrees == pytest.approx(54.7, rel=1e-4)

    def test_vtg_valid_true_when_fix_present(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_TPV_SPS)]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.vtg is not None
        assert data.vtg.valid is True

    def test_vtg_valid_false_when_no_fix(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_TPV_NO_FIX)]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.vtg is not None
        assert data.vtg.valid is False
        assert data.vtg.mode == "N"

    def test_vtg_mode_autonomous_for_gps_fix(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_TPV_SPS)]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.vtg is not None
        assert data.vtg.mode == "A"

    def test_vtg_mode_differential_for_dgps(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_TPV_DGPS)]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.vtg is not None
        assert data.vtg.mode == "D"

    def test_vtg_mode_differential_for_rtk_fixed(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_TPV_RTK)]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert data.vtg is not None
        assert data.vtg.mode == "D"

    def test_non_tpv_non_sky_messages_are_skipped(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [
            _line(_WATCH_MSG),
            _line(_VERSION_MSG),
            _line(_TPV_SPS),
        ]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert isinstance(data, GNSSData)
        assert data.gga.fix_quality == 1

    def test_invalid_json_lines_are_skipped(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [
            _GARBAGE.encode(),
            _line(_TPV_SPS),
        ]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert isinstance(data, GNSSData)

    def test_non_dict_json_lines_are_skipped(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [
            b"[1, 2, 3]\n",
            _line(_TPV_SPS),
        ]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert isinstance(data, GNSSData)

    def test_timeout_retried_until_tpv_arrives(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [
            TimeoutError(),
            _line(_TPV_SPS),
        ]
        with GNSSReader() as gnss:
            data = gnss.read()
        assert isinstance(data, GNSSData)

    def test_os_error_raises_eof_error(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = OSError("connection reset")
        with GNSSReader() as gnss, pytest.raises(EOFError):
            gnss.read()

    def test_empty_readline_raises_eof_error(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [b""]
        with GNSSReader() as gnss, pytest.raises(EOFError):
            gnss.read()


# ---------------------------------------------------------------------------
# GNSSReader - cancel
# ---------------------------------------------------------------------------


class TestGNSSReaderCancel:
    def test_cancel_raises_eof_error_on_next_read(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = OSError("simulated shutdown")
        with GNSSReader() as gnss:
            gnss.cancel()
            with pytest.raises(EOFError):
                gnss.read()

    def test_cancel_calls_socket_shutdown(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = OSError("simulated shutdown")
        with GNSSReader() as gnss:
            gnss.cancel()
            with contextlib.suppress(EOFError):
                gnss.read()
        mock_gpsd.sock.shutdown.assert_called_once()

    def test_cancel_during_timeout_raises_eof_error(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = TimeoutError()
        with GNSSReader() as gnss:
            gnss.cancel()
            with pytest.raises(EOFError):
                gnss.read()


# ---------------------------------------------------------------------------
# GNSSReader -- cleanup
# ---------------------------------------------------------------------------


class TestGNSSReaderCleanup:
    def test_closes_stream_and_socket_on_normal_exit(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [_line(_TPV_SPS)]
        with GNSSReader() as gnss:
            gnss.read()
        mock_gpsd.stream.close.assert_called_once()
        mock_gpsd.sock.close.assert_called_once()

    def test_closes_stream_and_socket_on_exception(self, mock_gpsd):
        with pytest.raises(ValueError, match="test"), GNSSReader():
            raise ValueError("test")
        mock_gpsd.stream.close.assert_called_once()
        mock_gpsd.sock.close.assert_called_once()


# ---------------------------------------------------------------------------
# GNSSReader -- __iter__
# ---------------------------------------------------------------------------


class TestGNSSReaderIter:
    def test_yields_gnss_data_instances(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [
            _line(_TPV_SPS),
            _line(_TPV_RTK),
            _line(_TPV_NO_FIX),
        ]
        with GNSSReader() as gnss:
            samples = list(itertools.islice(gnss, 3))
        assert len(samples) == 3
        assert all(isinstance(s, GNSSData) for s in samples)

    def test_iter_includes_vtg_from_first_tpv(self, mock_gpsd):
        mock_gpsd.stream.readline.side_effect = [
            _line(_TPV_SPS),
            _line(_TPV_RTK),
        ]
        with GNSSReader() as gnss:
            samples = list(itertools.islice(gnss, 2))
        assert samples[0].vtg is not None
        assert samples[0].vtg.mode == "A"
        assert samples[1].vtg is not None
        assert samples[1].vtg.mode == "D"
