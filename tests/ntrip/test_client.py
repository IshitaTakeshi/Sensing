"""Tests for the NTRIP client module."""

import base64
import io
import socket
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from sensing.ntrip import NTRIPClient, NTRIPConfig
from sensing.ntrip.client import _parse_status_code

_CFG = NTRIPConfig("rtk.example.com", 2101, "test-mount", "/dev/ttyAMA5")
_CFG_AUTH = NTRIPConfig(
    "rtk.example.com", 2101, "test-mount", "/dev/ttyAMA5",
    username="user", password="pass",  # noqa: S106
)


def _make_stream(headers: list[bytes], chunks: list[bytes]) -> MagicMock:
    """Return a mock BufferedReader with preset header and data responses."""
    mock = MagicMock(spec=io.BufferedReader)
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
# _build_request
# ---------------------------------------------------------------------------


class TestBuildRequest:
    def test_no_auth_first_line_is_correct(self):
        req = NTRIPClient(_CFG)._build_request().decode("ascii")
        assert req.split("\r\n")[0] == "GET /test-mount HTTP/1.0"

    def test_no_auth_has_no_authorization_header(self):
        req = NTRIPClient(_CFG)._build_request().decode("ascii")
        assert "Authorization" not in req

    def test_with_credentials_includes_basic_auth(self):
        req = NTRIPClient(_CFG_AUTH)._build_request().decode("ascii")
        expected = base64.b64encode(b"user:pass").decode()
        assert f"Authorization: Basic {expected}" in req


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
        mock_ntrip.serial.write.assert_called_once_with(rtcm)

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
