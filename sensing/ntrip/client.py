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


def _parse_status_code(first_line: str) -> int:
    """Parse the HTTP/NTRIP status code from the first response line.

    Supports both ``HTTP/1.0 200 OK`` and ``ICY 200 OK`` formats.
    Returns 0 if the line is malformed or the code is not an integer.
    """
    parts = first_line.split(None, 2)
    if len(parts) < 2:
        return 0
    try:
        return int(parts[1])
    except ValueError:
        return 0


def _read_headers(sock_file: io.BufferedReader) -> None:
    """Read NTRIP response headers; raise ConnectionError on non-200 status.

    Raises:
        ConnectionError: If the status code in the first response line is not 200.
    """
    first = sock_file.readline().decode("ascii", errors="replace").strip()
    if _parse_status_code(first) != 200:
        raise ConnectionError(f"NTRIP caster rejected connection: {first!r}")
    while True:
        line = sock_file.readline()
        if line in (b"\r\n", b"\n", b""):
            break


def _write_all(serial: io.RawIOBase, data: bytes) -> None:
    """Write all bytes to serial, retrying on partial writes.

    ``io.RawIOBase.write()`` may write fewer bytes than requested. Loop
    over a ``memoryview`` of the remaining data until all bytes are sent.

    Args:
        serial: Raw IO stream for the serial device.
        data: Bytes to write in full.

    Raises:
        OSError: If ``serial.write()`` returns ``None`` or makes no progress
            (returns 0), which would otherwise cause an infinite loop.
    """
    view = memoryview(data)
    while view:
        written = serial.write(view)
        if written is None or written <= 0:
            raise OSError(f"serial.write() returned {written!r} — no progress")
        view = view[written:]


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
            _write_all(serial, data)
        except TimeoutError:
            continue


def _build_request(cfg: NTRIPConfig) -> bytes:
    """Build an NTRIP v1 HTTP GET request for the given config."""
    lines = [
        f"GET /{cfg.mountpoint} HTTP/1.0",
        f"Host: {cfg.host}:{cfg.port}",
        "Ntrip-Version: Ntrip/1.0",
        "User-Agent: NTRIP sensing/1.0",
    ]
    auth = _basic_auth_header(cfg.username, cfg.password)
    if auth is not None:
        lines.append(auth)
    lines.extend(["", ""])
    return "\r\n".join(lines).encode("ascii")


def _basic_auth_header(username: str, password: str) -> str | None:
    """Return a Basic Auth header line, or ``None`` if either credential is empty.

    Both ``username`` and ``password`` must be non-empty to produce a header.
    Supplying only one is treated as no credentials to avoid sending a
    malformed ``:<password>`` or ``username:`` credential string.
    """
    if not username or not password:
        return None
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Authorization: Basic {creds}"


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

    def stream(self) -> None:
        """Connect to the NTRIP caster and forward RTCM3 to serial. Blocks until done.

        Raises:
            ConnectionError: If the caster returns a non-200 response.
        """
        cfg = self._config
        address = (cfg.host, cfg.port)
        with socket.create_connection(address, timeout=_SOCKET_TIMEOUT) as sock:
            sock.sendall(_build_request(cfg))
            with sock.makefile("rb") as sock_file:
                _read_headers(sock_file)
                with open(cfg.serial_device, "wb", buffering=0) as serial:
                    _forward(sock_file, serial, self._cancel)
