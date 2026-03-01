"""GNSSReader: gpsd JSON client for GNSS data streaming.

Connects to a local gpsd instance over TCP (localhost:2947) instead of
opening the serial port directly. This allows the server to coexist with
gpsd, which feeds NMEA sentences to Chrony via shared memory (SHM 0) for
time synchronization.

Reading strategy:
    gpsd emits newline-delimited JSON on its client socket. TPV messages
    supply position, fix quality, speed, and track. SKY messages supply
    satellite count and HDOP. On each TPV event the most recently received
    SKY fields are merged to produce a GNSSData, mirroring the GGA+VTG
    pairing of the former serial reader.
"""

import contextlib
import json
import socket
from collections.abc import Iterator
from types import TracebackType
from typing import IO, Any

from sensing.gnss.types import GNSSData
from sensing.nmea.types import GGAData, VTGData

__all__ = ["GNSSReader"]

# --- gpsd connection defaults -------------------------------------------------

_HOST = "localhost"
_PORT = 2947
_TIMEOUT = 2.0  # socket read timeout; determines maximum cancel() latency

_WATCH_CMD = b'?WATCH={"enable":true,"json":true}\n'

# --- unit conversions ---------------------------------------------------------

_MPS_TO_KNOTS = 1.94384
_MPS_TO_KPH = 3.6

# --- gpsd status codes --------------------------------------------------------

# gpsd TPV.status -> NMEA GGA fix_quality
# Source: https://gpsd.gitlab.io/gpsd/gpsd_json.html
_STATUS_TO_FIX_QUALITY: dict[int, int] = {
    0: 0,  # No fix    -> Invalid
    1: 1,  # Normal    -> GPS fix (SPS)
    2: 2,  # DGPS      -> DGPS fix
    3: 4,  # RTK Fixed -> RTK Fixed
    4: 5,  # RTK Float -> RTK Float
    5: 6,  # DR        -> Dead reckoning
}

# gpsd TPV.status -> NMEA VTG FAA mode indicator
_STATUS_TO_VTG_MODE: dict[int, str] = {
    0: "N",  # No fix     -> Not valid
    1: "A",  # Normal GPS -> Autonomous
    2: "D",  # DGPS       -> Differential
    3: "D",  # RTK Fixed  -> Differential
    4: "D",  # RTK Float  -> Differential
    5: "E",  # DR         -> Estimated
}


# --- helpers ------------------------------------------------------------------


def _iso_to_utc_time(iso: str) -> str:
    """Convert an ISO 8601 UTC timestamp to HHMMSS.ss format.

    For example ``"2025-03-01T12:35:19.000Z"`` becomes ``"123519.00"``.
    """
    # "2025-03-01T12:35:19.000Z" -> slice off the time part after 'T'
    t = iso[11:]  # "12:35:19.000Z"
    hh = t[0:2]
    mm = t[3:5]
    ss_rest = t[6:].rstrip("Z")  # "19.000" or "19"
    if "." in ss_rest:
        ss, frac = ss_rest.split(".", 1)
        return f"{hh}{mm}{ss}.{frac[:2].ljust(2, '0')}"
    return f"{hh}{mm}{ss_rest}.00"


# --- public API ---------------------------------------------------------------


class GNSSReader:
    """Context manager for reading GNSS data from a gpsd JSON stream.

    Connects to a local gpsd instance over TCP and consumes its
    newline-delimited JSON stream. TPV messages provide position, fix
    quality, speed, and track; SKY messages provide satellite count and
    HDOP. On each TPV event the most recently received SKY fields are
    merged with the TPV fields to produce a ``GNSSData``.

    Two consumption patterns are supported:

    Continuous iteration (recommended for server backends)::

        with GNSSReader() as gnss:
            for data in gnss:
                process(data)

    Single read (useful for one-shot or polling scenarios)::

        with GNSSReader() as gnss:
            data = gnss.read()

    Each emitted ``GNSSData`` contains:

    * ``gga`` - position, fix quality, satellite count, and HDOP assembled
      from the TPV and the most recent SKY message. ``gga.valid`` is
      ``False`` when gpsd reports no fix.
    * ``vtg`` - velocity assembled from the same TPV message.
      ``vtg.valid`` is ``False`` when there is no fix.

    Args:
        host: gpsd host (default: ``"localhost"``).
        port: gpsd TCP port (default: ``2947``).
    """

    def __init__(
        self,
        host: str = _HOST,
        port: int = _PORT,
    ) -> None:
        """Store connection parameters; the socket is opened in ``__enter__``."""
        self._host = host
        self._port = port
        self._sock: socket.socket | None = None
        self._stream: IO[Any] | None = None
        self._cancelled: bool = False
        self._last_num_satellites: int | None = None
        self._last_hdop: float | None = None

    def __enter__(self) -> "GNSSReader":
        """Open the gpsd connection and reset internal state."""
        self._sock = socket.create_connection((self._host, self._port))
        self._sock.settimeout(_TIMEOUT)
        self._sock.sendall(_WATCH_CMD)
        self._stream = self._sock.makefile("rb")
        self._cancelled = False
        self._last_num_satellites = None
        self._last_hdop = None
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the gpsd connection."""
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def cancel(self) -> None:
        """Cancel pending blocking reads gracefully.

        Sets the cancellation flag and shuts down the socket so that any
        in-progress ``readline()`` unblocks immediately and raises
        ``EOFError``, allowing background threads to exit without waiting
        for the next timeout cycle.
        """
        self._cancelled = True
        if self._sock is not None:
            with contextlib.suppress(OSError):
                self._sock.shutdown(socket.SHUT_RDWR)

    def _recv_raw(self, stream: IO[Any]) -> bytes | None:
        """Read one raw line from gpsd; returns ``None`` on timeout retry.

        Raises:
            EOFError: If the stream ended or the connection was closed.
        """
        try:
            raw: bytes = stream.readline()
            if not raw:
                raise EOFError("gpsd stream ended.")
            return raw
        except TimeoutError:
            return None
        except OSError as e:
            raise EOFError("gpsd connection closed.") from e

    def _read_line(self) -> str | None:
        """Read and decode one JSON line; returns ``None`` on timeout retry.

        Raises:
            RuntimeError: If called outside a ``with`` block.
            EOFError: If cancelled, or the stream ended or was closed.
        """
        if self._stream is None:
            raise RuntimeError("GNSSReader must be used as a context manager.")
        raw = self._recv_raw(self._stream)
        if raw is None and self._cancelled:
            raise EOFError("gpsd read cancelled.")
        if raw is None:
            return None
        return raw.decode("utf-8", errors="ignore").strip()

    def _process_sky(self, msg: dict[str, Any]) -> None:
        """Update stored satellite count and HDOP from a SKY message."""
        # uSat = satellites used in fix (gpsd >= 3.19); fall back to nSat
        u_sat: int | None = msg.get("uSat")
        self._last_num_satellites = u_sat if u_sat is not None else msg.get("nSat")
        self._last_hdop = msg.get("hdop")

    def _build_gga(
        self,
        msg: dict[str, Any],
        fix_quality: int,
        utc_time: str | None,
    ) -> GGAData:
        """Assemble a ``GGAData`` from TPV message fields and stored SKY state."""
        # gpsd >= 3.25 renamed alt (MSL) to altMSL and added altHAE
        alt: float | None = msg.get("altMSL")
        if alt is None:
            alt = msg.get("alt")
        return GGAData(
            utc_time=utc_time,
            latitude_degrees=msg.get("lat"),
            longitude_degrees=msg.get("lon"),
            fix_quality=fix_quality,
            num_satellites=self._last_num_satellites,
            horizontal_dilution_of_precision=self._last_hdop,
            altitude_meters=alt,
            geoid_height_meters=None,
            valid=fix_quality > 0,
        )

    def _build_vtg(self, msg: dict[str, Any], status: int) -> VTGData:
        """Assemble a ``VTGData`` from TPV message fields."""
        speed_mps: float | None = msg.get("speed")
        track: float | None = msg.get("track")
        vtg_mode = _STATUS_TO_VTG_MODE.get(status, "N")
        kph = speed_mps * _MPS_TO_KPH if speed_mps is not None else None
        return VTGData(
            track_true_degrees=track,
            speed_knots=speed_mps * _MPS_TO_KNOTS if speed_mps is not None else None,
            speed_kilometers_per_hour=kph,
            speed_meters_per_second=speed_mps,
            mode=vtg_mode,
            valid=vtg_mode != "N",
        )

    def _process_tpv(self, msg: dict[str, Any]) -> GNSSData:
        """Assemble a ``GNSSData`` from a TPV message and stored SKY state."""
        status: int = msg.get("status", 0)
        fix_quality = _STATUS_TO_FIX_QUALITY.get(status, 0)
        iso_time: str | None = msg.get("time")
        utc_time = _iso_to_utc_time(iso_time) if iso_time else None
        gga = self._build_gga(msg, fix_quality, utc_time)
        vtg = self._build_vtg(msg, status)
        return GNSSData(gga=gga, vtg=vtg)

    def _dispatch(self, line: str) -> GNSSData | None:
        """Parse one JSON line, update state, and return data on TPV."""
        try:
            msg: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            return None
        cls = msg.get("class")
        if cls == "SKY":
            self._process_sky(msg)
        elif cls == "TPV":
            return self._process_tpv(msg)
        return None

    def read(self) -> GNSSData:
        """Block until the next TPV message and return a combined GNSS sample.

        Raises:
            RuntimeError: If called outside a ``with`` block.
            EOFError: If the read is cancelled or the stream ends.
        """
        if self._sock is None:
            raise RuntimeError("GNSSReader must be used as a context manager.")
        while True:
            line = self._read_line()
            if line is None:
                continue
            result = self._dispatch(line)
            if result is not None:
                return result

    def __iter__(self) -> Iterator[GNSSData]:
        """Yield GNSS samples indefinitely, one per TPV message.

        Iteration continues until the caller breaks the loop or an exception
        propagates out (e.g. ``EOFError`` on cancellation). ``StopIteration``
        is never raised.

        Yields:
            ``GNSSData`` for each received TPV message.
        """
        while True:
            yield self.read()
