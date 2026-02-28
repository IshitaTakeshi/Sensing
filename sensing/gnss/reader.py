"""GNSSReader: serial NMEA stream reader for u-blox ZED-F9P.

Hardware configuration:
    UART5 on Raspberry Pi 4B → /dev/ttyAMA5 at 38400 bps
    u-blox ZED-F9P outputs GGA + VTG sentences at approximately 1 Hz.

Reading strategy:
    Lines are consumed one at a time. VTG sentences update internal state.
    GGA sentences trigger a ``GNSSData`` yield containing the GGA data paired
    with the most recently received VTG. All other sentence types are silently
    skipped. Sentences that fail checksum validation are also discarded.
"""

from collections.abc import Iterator
from types import TracebackType
from typing import TYPE_CHECKING

import serial  # type: ignore[import-untyped]

from sensing.gnss.types import GNSSData
from sensing.nmea.gga import parse_gga
from sensing.nmea.vtg import parse_vtg

if TYPE_CHECKING:
    from sensing.nmea.types import VTGData

# --- Hardware defaults -------------------------------------------------------

_PORT = "/dev/ttyAMA5"
_BAUDRATE = 38400
_TIMEOUT = 2.0  # seconds; enough for a full 1 Hz sentence cycle


# --- Public API --------------------------------------------------------------


class GNSSReader:
    """Context manager for reading GNSS data from a serial NMEA 0183 stream.

    Manages the serial port for the lifetime of the ``with`` block. On entry
    the port is opened; on exit it is closed regardless of exceptions. Two
    consumption patterns are supported:

    Continuous iteration (recommended for server backends)::

        with GNSSReader() as gnss:
            for data in gnss:
                process(data)

    Single read (useful for one-shot or polling scenarios)::

        with GNSSReader() as gnss:
            data = gnss.read()

    Each emitted ``GNSSData`` contains:

    * ``gga`` — the freshly parsed GGA sentence (always present, may have
      ``valid=False`` when there is no fix).
    * ``vtg`` — the most recently received VTG sentence, or ``None`` until
      the first VTG has been seen.

    Args:
        port: Serial device path (default: ``/dev/ttyAMA5``).
        baudrate: Baud rate matching the receiver configuration (default: 38400).
    """

    def __init__(
        self,
        port: str = _PORT,
        baudrate: int = _BAUDRATE,
    ) -> None:
        """Store connection parameters; the port is opened in ``__enter__``."""
        self._port = port
        self._baudrate = baudrate
        self._serial: serial.Serial | None = None
        self._last_vtg: VTGData | None = None

    def __enter__(self) -> "GNSSReader":
        """Open the serial port and reset internal VTG state."""
        self._serial = serial.Serial(
            self._port,
            baudrate=self._baudrate,
            timeout=_TIMEOUT,
        )
        self._last_vtg = None
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the serial port."""
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def _process_line(self, line: str) -> GNSSData | None:
        vtg = parse_vtg(line)
        if vtg is not None:
            self._last_vtg = vtg
            return None
        gga = parse_gga(line)
        if gga is not None:
            return GNSSData(gga=gga, vtg=self._last_vtg)
        return None

    def cancel(self) -> None:
        """Cancel pending blocking reads gracefully.

        Uses the underlying serial implementation to cancel I/O, allowing
        background threads to exit cleanly without waiting for timeouts.
        """
        if self._serial is None:
            return
        self._serial.cancel_read()

    def read(self) -> GNSSData:
        """Block until the next GGA sentence and return a combined GNSS sample.

        Raises:
            RuntimeError: If called outside a ``with`` block.
            EOFError: If the read is cancelled or the stream ends.
        """
        if self._serial is None:
            raise RuntimeError("GNSSReader must be used as a context manager.")
        while True:
            line = self._serial.readline().decode("ascii", errors="ignore")
            if not line:
                raise EOFError("Serial port read cancelled.")

            result = self._process_line(line)
            if result is not None:
                return result

    def __iter__(self) -> Iterator[GNSSData]:
        """Yield GNSS samples indefinitely, one per GGA sentence.

        Iteration continues until the caller breaks the loop or an exception
        propagates out (e.g. serial read error). ``StopIteration`` is never
        raised.

        Yields:
            ``GNSSData`` for each received GGA sentence.
        """
        while True:
            yield self.read()
