"""Tests for the NTRIP client module."""

import base64
import io
import socket
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from sensing.nmea.types import GGAData
from sensing.ntrip import NTRIPClient, NTRIPConfig
from sensing.ntrip.client import (
    _basic_auth_header,
    _build_request,
    _parse_status_code,
    _write_all,
)

_CFG = NTRIPConfig("rtk.example.com", 2101, "test-mount", "/dev/ttyAMA5")
_CFG_AUTH = NTRIPConfig(
    "rtk.example.com", 2101, "test-mount", "/dev/ttyAMA5",
    username="user", password="pass",  # noqa: S106
)
_CFG_GGA = NTRIPConfig(
    "rtk.example.com", 2101, "test-mount", "/dev/ttyAMA5",
    gga_interval_seconds=10.0,
)

# Tokyo Tower -- public landmark used to avoid privacy-sensitive coordinates.
_GGA_DATA = GGAData(
    utc_time="123519.00",
    latitude_degrees=35.6586,
    longitude_degrees=139.7454,
    fix_quality=1,
    num_satellites=8,
    horizontal_dilution_of_precision=0.9,
    altitude_meters=333.0,
    geoid_height_meters=None,
    valid=True,
)


def _make_stream(headers: list[bytes], chunks: list[bytes]) -> MagicMock:
    """Return a mock BufferedReader with preset header and data responses."""
    mock = MagicMock(spec=io.BufferedReader)
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    mock.readline.side_effect = headers
    mock.read1.side_effect = chunks
    return mock


@pytest.fixture
def mock_ntrip(monkeypatch):
    """Fixture: mock socket.create_connection and builtins.open.

    Returns a SimpleNamespace with attributes:
        sock    -- the socket mock (used as context manager)
        serial  -- the serial file mock (used as context manager)
    """
    sock = MagicMock()
    sock.__enter__ = MagicMock(return_value=sock)
    sock.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(socket, "create_connection", MagicMock(return_value=sock))

    serial = MagicMock()
    serial.__enter__ = MagicMock(return_value=serial)
    serial.__exit__ = MagicMock(return_value=False)
    serial.write.side_effect = len  # simulate a full write every call
    monkeypatch.setattr("builtins.open", MagicMock(return_value=serial))

    return SimpleNamespace(sock=sock, serial=serial)


# ---------------------------------------------------------------------------
# _parse_status_code
# ---------------------------------------------------------------------------


class TestParseStatusCode:
    def test_http_200(self):
        assert _parse_status_code("HTTP/1.0 200 OK") == 200

    def test_icy_200(self):
        assert _parse_status_code("ICY 200 OK") == 200

    def test_http_401(self):
        assert _parse_status_code("HTTP/1.0 401 Unauthorized") == 401

    def test_line_containing_200_but_non_200_code(self):
        assert _parse_status_code("HTTP/1.0 404 Error 200 details") == 404

    def test_malformed_returns_zero(self):
        assert _parse_status_code("GARBAGE") == 0


# ---------------------------------------------------------------------------
# _basic_auth_header
# ---------------------------------------------------------------------------


class TestBasicAuthHeader:
    def test_both_set_returns_header(self):
        header = _basic_auth_header("user", "pass")
        assert header is not None
        assert header.startswith("Authorization: Basic ")

    def test_only_username_returns_none(self):
        assert _basic_auth_header("user", "") is None

    def test_only_password_returns_none(self):
        assert _basic_auth_header("", "pass") is None

    def test_both_empty_returns_none(self):
        assert _basic_auth_header("", "") is None


# ---------------------------------------------------------------------------
# _build_request
# ---------------------------------------------------------------------------


class TestBuildRequest:
    def test_no_auth_first_line_is_correct(self):
        req = _build_request(_CFG).decode("ascii")
        assert req.split("\r\n")[0] == "GET /test-mount HTTP/1.0"

    def test_no_auth_has_no_authorization_header(self):
        req = _build_request(_CFG).decode("ascii")
        assert "Authorization" not in req

    def test_with_credentials_includes_basic_auth(self):
        req = _build_request(_CFG_AUTH).decode("ascii")
        expected = base64.b64encode(b"user:pass").decode()
        assert f"Authorization: Basic {expected}" in req


# ---------------------------------------------------------------------------
# _write_all
# ---------------------------------------------------------------------------


class TestWriteAll:
    def test_single_write_completes(self):
        serial = MagicMock(spec=io.RawIOBase)
        data = b"\xD3\x00\x13"
        serial.write.return_value = len(data)
        _write_all(serial, data)
        serial.write.assert_called_once()

    def test_partial_write_retries_remainder(self):
        serial = MagicMock(spec=io.RawIOBase)
        data = b"\xD3\x00\x13\x43\x50"
        serial.write.side_effect = [2, 3]
        _write_all(serial, data)
        assert serial.write.call_count == 2

    def test_none_return_raises_os_error(self):
        serial = MagicMock(spec=io.RawIOBase)
        serial.write.return_value = None
        with pytest.raises(OSError, match="no progress"):
            _write_all(serial, b"\xD3\x00")

    def test_zero_return_raises_os_error(self):
        serial = MagicMock(spec=io.RawIOBase)
        serial.write.return_value = 0
        with pytest.raises(OSError, match="no progress"):
            _write_all(serial, b"\xD3\x00")


# ---------------------------------------------------------------------------
# TestStream
# ---------------------------------------------------------------------------


class TestStream:
    def test_icy_200_writes_rtcm3_to_serial(self, mock_ntrip):
        rtcm = b"\xD3\x00\x13\x43\x50"
        mock_ntrip.sock.makefile.return_value = _make_stream(
            [b"ICY 200 OK\r\n", b"\r\n"], [rtcm, b""]
        )
        with NTRIPClient(_CFG) as client:
            client.stream()
        written = b"".join(bytes(call.args[0]) for call in mock_ntrip.serial.write.call_args_list)
        assert written == rtcm

    def test_non_200_raises_connection_error(self, mock_ntrip):
        mock_ntrip.sock.makefile.return_value = _make_stream(
            [b"HTTP/1.0 401 Unauthorized\r\n"], []
        )
        with NTRIPClient(_CFG) as client, pytest.raises(ConnectionError):
            client.stream()

    def test_cancel_stops_forward_loop(self, mock_ntrip):
        mock_ntrip.sock.makefile.return_value = _make_stream(
            [b"ICY 200 OK\r\n", b"\r\n"], []
        )
        with NTRIPClient(_CFG) as client:
            client.cancel()
            client.stream()
        mock_ntrip.serial.write.assert_not_called()


# ---------------------------------------------------------------------------
# TestStreamWithGga
# ---------------------------------------------------------------------------


class TestStreamWithGga:
    def test_gga_is_sent_to_caster_socket(self, mock_ntrip):
        mock_ntrip.sock.makefile.return_value = _make_stream(
            [b"ICY 200 OK\r\n", b"\r\n"], [b""]
        )
        with NTRIPClient(_CFG_GGA, gga_provider=lambda: _GGA_DATA) as client:
            client.stream()
        mock_ntrip.sock.sendall.assert_called()
        sent = mock_ntrip.sock.sendall.call_args[0][0]
        assert sent.startswith(b"$GPGGA,")
        assert sent.endswith(b"\r\n")

    def test_gga_contains_expected_latitude(self, mock_ntrip):
        mock_ntrip.sock.makefile.return_value = _make_stream(
            [b"ICY 200 OK\r\n", b"\r\n"], [b""]
        )
        with NTRIPClient(_CFG_GGA, gga_provider=lambda: _GGA_DATA) as client:
            client.stream()
        sent = mock_ntrip.sock.sendall.call_args[0][0].decode()
        assert "3539.5160" in sent

    def test_no_gga_sent_when_provider_returns_none(self, mock_ntrip):
        mock_ntrip.sock.makefile.return_value = _make_stream(
            [b"ICY 200 OK\r\n", b"\r\n"], [b""]
        )
        with NTRIPClient(_CFG_GGA, gga_provider=lambda: None) as client:
            client.stream()
        gga_calls = [c for c in mock_ntrip.sock.sendall.call_args_list if b"$GPGGA" in c.args[0]]
        assert gga_calls == []

    def test_no_gga_sent_when_provider_is_absent(self, mock_ntrip):
        mock_ntrip.sock.makefile.return_value = _make_stream(
            [b"ICY 200 OK\r\n", b"\r\n"], [b""]
        )
        with NTRIPClient(_CFG) as client:
            client.stream()
        gga_calls = [c for c in mock_ntrip.sock.sendall.call_args_list if b"$GPGGA" in c.args[0]]
        assert gga_calls == []

    def test_no_gga_sent_when_coordinates_are_none(self, mock_ntrip):
        mock_ntrip.sock.makefile.return_value = _make_stream(
            [b"ICY 200 OK\r\n", b"\r\n"], [b""]
        )
        no_fix = GGAData(
            utc_time=None, latitude_degrees=None, longitude_degrees=None,
            fix_quality=0, num_satellites=None, horizontal_dilution_of_precision=None,
            altitude_meters=None, geoid_height_meters=None, valid=False,
        )
        with NTRIPClient(_CFG_GGA, gga_provider=lambda: no_fix) as client:
            client.stream()
        gga_calls = [c for c in mock_ntrip.sock.sendall.call_args_list if b"$GPGGA" in c.args[0]]
        assert gga_calls == []
