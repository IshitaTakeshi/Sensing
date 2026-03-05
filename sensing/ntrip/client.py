"""NTRIP v1 client: streams RTCM3 corrections to a serial device."""

import base64
import io
import socket
import threading
import time
from collections.abc import Callable
from types import TracebackType

from sensing.nmea.formatter import format_gga
from sensing.nmea.types import GGAData
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


def _drain_headers(sock_file: io.BufferedReader, cancel: threading.Event) -> None:
    """Read and discard header lines until a blank line or cancel is set.

    Args:
        sock_file: Buffered reader wrapping the NTRIP TCP socket.
        cancel: Event that signals the loop to stop.
    """
    while not cancel.is_set():
        try:
            line = sock_file.readline()
        except TimeoutError:
            continue
        if line in (b"\r\n", b"\n", b""):
            return


def _check_status(sock_file: io.BufferedReader) -> None:
    """Read the first response line and raise on a non-200 status code.

    Args:
        sock_file: Buffered reader wrapping the NTRIP TCP socket.

    Raises:
        ConnectionError: If the status code in the first response line is not 200.
    """
    first = sock_file.readline().decode("ascii", errors="replace").strip()
    if _parse_status_code(first) != 200:
        raise ConnectionError(f"NTRIP caster rejected connection: {first!r}")


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


def _make_gga_sender(
    sock: socket.socket,
    gga_provider: Callable[[], GGAData | None],
) -> Callable[[], None]:
    """Return a callable that fetches the rover's GGA and sends it to the caster."""
    def _send() -> None:
        """Fetch the current position and send it upstream as a NMEA GGA sentence."""
        gga = gga_provider()
        if gga is None:
            return
        if gga.latitude_degrees is None or gga.longitude_degrees is None:
            return
        sock.sendall(format_gga(gga).encode("ascii"))
    return _send


def _maybe_send_gga(
    gga_sender: Callable[[], None] | None,
    last_gga: float,
    gga_interval: float,
) -> float:
    """Send a GGA sentence if the interval has elapsed; return the updated timestamp.

    Args:
        gga_sender: Callable that sends one GGA sentence, or ``None`` to skip.
        last_gga: ``time.monotonic()`` value from the previous GGA send.
        gga_interval: Minimum seconds between consecutive GGA sends.

    Returns:
        Updated ``last_gga`` timestamp (unchanged if no send occurred).
    """
    if gga_sender is None:
        return last_gga
    now = time.monotonic()
    if now - last_gga < gga_interval:
        return last_gga
    gga_sender()
    return now


def _forward(
    source: io.BufferedReader,
    serial: io.RawIOBase,
    cancel: threading.Event,
    gga_sender: Callable[[], None] | None,
    gga_interval: float,
) -> None:
    """Forward RTCM3 bytes from source to serial until cancel is set or EOF.

    If ``gga_sender`` is provided, it is called every ``gga_interval`` seconds
    to send the rover's current position upstream to the NTRIP caster (required
    by VRS services).

    Args:
        source: Buffered reader wrapping the NTRIP TCP socket.
        serial: Raw IO stream for the serial device.
        cancel: Event that signals the loop to stop.
        gga_sender: Optional callable that sends a GGA sentence to the caster.
        gga_interval: Minimum seconds between consecutive GGA sends.
    """
    last_gga = 0.0
    while not cancel.is_set():
        try:
            last_gga = _maybe_send_gga(gga_sender, last_gga, gga_interval)
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
        gga_provider: Optional callable returning the rover's current position.
            When provided, the client sends a GGA sentence to the caster after
            the handshake and every ``config.gga_interval_seconds`` thereafter.
            Required by VRS-type casters to generate geographically tailored
            corrections. When ``None`` or when the provider returns ``None``,
            no GGA is sent (suitable for single-base casters).
    """

    def __init__(
        self,
        config: NTRIPConfig,
        gga_provider: Callable[[], GGAData | None] | None = None,
    ) -> None:
        """Store config and optional GGA provider; connection is made in ``stream``."""
        self._config = config
        self._cancel = threading.Event()
        self._gga_provider = gga_provider

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
                _check_status(sock_file)
                _drain_headers(sock_file, self._cancel)
                if self._cancel.is_set():
                    return
                gga_sender = None
                if self._gga_provider is not None:
                    gga_sender = _make_gga_sender(sock, self._gga_provider)
                interval = cfg.gga_interval_seconds
                with open(cfg.serial_device, "wb", buffering=0) as serial:
                    _forward(sock_file, serial, self._cancel, gga_sender, interval)
