"""NTRIP v1 client: streams RTCM3 corrections to a serial device."""

import base64
import io
import socket
import threading
from types import TracebackType

from sensing.ntrip.config import NTRIPConfig

__all__ = ["NTRIPClient"]

_SOCKET_TIMEOUT = 1.0  # seconds; determines maximum cancel() latency
_CHUNK = 4096


def _read_headers(sock_file: io.BufferedReader) -> None:
    """Read NTRIP response headers; raise ConnectionError on non-200 status.

    Raises:
        ConnectionError: If the first response line does not contain ``200``.
    """
    first = sock_file.readline().decode("ascii", errors="replace").strip()
    if "200" not in first:
        raise ConnectionError(f"NTRIP caster rejected connection: {first!r}")
    while True:
        line = sock_file.readline()
        if line in (b"\r\n", b"\n", b""):
            break


def _forward(
    source: io.BufferedReader,
    serial: io.RawIOBase,
    cancel: threading.Event,
) -> None:
    """Forward RTCM3 bytes from source to serial until cancel is set or EOF.

    Args:
        source: Buffered reader wrapping the NTRIP TCP socket.
        serial: Raw IO stream for the serial device.
        cancel: Event that signals the loop to stop.
    """
    while not cancel.is_set():
        try:
            data = source.read1(_CHUNK)
            if not data:
                break
            serial.write(data)
        except TimeoutError:
            continue


class NTRIPClient:
    """Context manager for streaming RTCM3 from an NTRIP caster to a serial device.

    Args:
        config: NTRIP caster and serial device parameters.
    """

    def __init__(self, config: NTRIPConfig) -> None:
        """Store config; the connection is made in ``stream()``."""
        self._config = config
        self._cancel = threading.Event()

    def __enter__(self) -> "NTRIPClient":
        """Clear the cancel event so the client can be reused after ``cancel()``."""
        self._cancel.clear()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Cancel any in-progress ``stream()`` call."""
        self.cancel()

    def cancel(self) -> None:
        """Signal ``stream()`` to stop forwarding data."""
        self._cancel.set()

    def _build_request(self) -> bytes:
        """Build an NTRIP v1 HTTP GET request."""
        cfg = self._config
        lines = [
            f"GET /{cfg.mountpoint} HTTP/1.0",
            f"Host: {cfg.host}:{cfg.port}",
            "Ntrip-Version: Ntrip/1.0",
            "User-Agent: NTRIP sensing/1.0",
        ]
        if cfg.username or cfg.password:
            creds = base64.b64encode(f"{cfg.username}:{cfg.password}".encode()).decode()
            lines.append(f"Authorization: Basic {creds}")
        lines.extend(["", ""])
        return "\r\n".join(lines).encode("ascii")

    def stream(self) -> None:
        """Connect to the NTRIP caster and forward RTCM3 to serial. Blocks until done.

        Raises:
            ConnectionError: If the caster returns a non-200 response.
        """
        cfg = self._config
        with socket.create_connection((cfg.host, cfg.port)) as sock:
            sock.sendall(self._build_request())
            sock_file: io.BufferedReader = sock.makefile("rb")
            _read_headers(sock_file)
            sock.settimeout(_SOCKET_TIMEOUT)
            with open(cfg.serial_device, "wb", buffering=0) as serial:
                _forward(sock_file, serial, self._cancel)
