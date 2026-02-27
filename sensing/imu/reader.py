"""ISM330DHCX IMU reader using SPI and GPIO DRDY interrupt.

Hardware configuration (fixed register values):
    Accelerometer: FS=±2g,      ODR=104 Hz  (CTRL1_XL = 0x40)
    Gyroscope:     FS=±2000 dps, ODR=104 Hz  (CTRL2_G  = 0x4C)
    INT1 pin:      DRDY_A (accelerometer data-ready, bit 0 of INT1_CTRL)

SPI protocol notes:
    - Read access: set bit 7 of the register address (OR with 0x80)
    - Auto-increment: enabled via CTRL3_C bit 2 (IF_INC=1), allowing
      burst reads across consecutive registers in a single transfer
    - Output registers are little-endian signed 16-bit integers

Sensitivity note:
    The gyroscope FS=±2000 dps setting does not mean the full-scale range
    is exactly 2000 dps. The datasheet specifies 70 mdps/LSB (TYP), so the
    true full-scale at int16 max (32767 LSB) is 32767 * 70e-3 = 2293.7 dps.
    Always derive physical values from the sensitivity constant, not the
    range label.
"""

import math
import struct
import time
from collections.abc import Iterator
from types import TracebackType

import gpiod
import spidev  # type: ignore[import-not-found]
from gpiod.line import Direction, Edge

from sensing.imu.types import IMUData

# --- Hardware defaults -------------------------------------------------------

_GPIO_CHIP = "/dev/gpiochip4"
_GPIO_LINE = 25
_SPI_BUS = 0
_SPI_DEVICE = 0
_SPI_MAX_SPEED_HZ = 5_000_000

# --- ISM330DHCX register addresses ------------------------------------------

_REG_INT1_CTRL = 0x0D
_REG_CTRL1_XL = 0x10
_REG_CTRL2_G = 0x11
_REG_CTRL3_C = 0x12

# First output register: gyro X/Y/Z (0x22-0x27) then accel X/Y/Z (0x28-0x2D)
_REG_OUTX_L_G = 0x22

# --- Sensitivity constants ---------------------------------------------------
# Derived from ISM330DHCX datasheet: Table 2 (accel) and Table 3 (gyro).
#
# Accelerometer FS=±2g: 0.061 mg/LSB
_ACCEL_SENSITIVITY: float = 0.061e-3 * 9.80665  # m/s² per LSB

# Gyroscope FS=±2000 dps: 70 mdps/LSB
_GYRO_SENSITIVITY: float = 70.0e-3 * (math.pi / 180.0)  # rad/s per LSB


# --- Private hardware helpers ------------------------------------------------


def _reset_imu(spi: spidev.SpiDev) -> None:
    """Software-reset the IMU into a known stopped state.

    Issues SW_RESET (CTRL3_C bit 0), waits for the reset to complete,
    then enables Block Data Update (BDU) and address auto-increment
    (IF_INC). The IMU remains stopped (ODR=0) until _start_imu is called.

    Args:
        spi: Open SpiDev instance.
    """
    spi.xfer2([_REG_CTRL3_C, 0x01])  # SW_RESET
    time.sleep(0.1)
    spi.xfer2([_REG_CTRL3_C, 0x44])  # BDU=1, IF_INC=1


def _start_imu(spi: spidev.SpiDev) -> None:
    """Begin IMU measurements.

    Enables DRDY_A on INT1, starts the gyroscope, then starts the
    accelerometer. Writing CTRL1_XL last is intentional: it triggers the
    shared measurement cycle, so GPIO edge detection must already be active
    before this is called.

    Args:
        spi: Open SpiDev instance with BDU and IF_INC configured.
    """
    spi.xfer2([_REG_INT1_CTRL, 0x01])  # INT1_DRDY_A
    spi.xfer2([_REG_CTRL2_G, 0x4C])  # Gyro  104 Hz, FS=±2000 dps
    spi.xfer2([_REG_CTRL1_XL, 0x40])  # Accel 104 Hz, FS=±2g  (starts cycle)


def _parse_sample(raw: bytes, timestamp: float) -> IMUData:
    """Convert 12 raw output register bytes into an IMUData with physical units.

    The 12 bytes contain six consecutive little-endian signed 16-bit integers
    in the order: gyro X, gyro Y, gyro Z, accel X, accel Y, accel Z.
    Sensitivities are fixed to the current hardware configuration
    (accel FS=±2g, gyro FS=±2000 dps).

    Args:
        raw: Exactly 12 bytes from registers OUTX_L_G (0x22) through
            OUTZ_H_A (0x2D), with gyro X/Y/Z followed by accel X/Y/Z.
        timestamp: CLOCK_REALTIME seconds captured at the DRDY interrupt edge.

    Returns:
        IMUData with accelerometer values in m/s² and gyroscope in rad/s.
    """
    gx, gy, gz, ax, ay, az = struct.unpack("<hhhhhh", raw)
    return IMUData(
        timestamp=timestamp,
        accel_x=ax * _ACCEL_SENSITIVITY,
        accel_y=ay * _ACCEL_SENSITIVITY,
        accel_z=az * _ACCEL_SENSITIVITY,
        gyro_x=gx * _GYRO_SENSITIVITY,
        gyro_y=gy * _GYRO_SENSITIVITY,
        gyro_z=gz * _GYRO_SENSITIVITY,
    )


def _read_sample(spi: spidev.SpiDev, timestamp: float) -> IMUData:
    """Issue a 12-byte SPI burst read and delegate conversion to _parse_sample.

    Sends a single read command starting at OUTX_L_G (0x22) with the read
    bit set (bit 7). Auto-increment (IF_INC=1) must be enabled beforehand so
    the device streams all 12 output registers in one transfer.

    Args:
        spi: Open SpiDev instance with IF_INC enabled.
        timestamp: CLOCK_REALTIME seconds at the triggering DRDY edge.

    Returns:
        IMUData with accelerometer values in m/s² and gyroscope in rad/s.
    """
    msg = [_REG_OUTX_L_G | 0x80] + [0x00] * 12
    resp = spi.xfer2(msg)
    return _parse_sample(bytes(resp[1:13]), timestamp)


# --- Public API --------------------------------------------------------------


class IMUReader:
    """Context manager for reading IMU data from an ISM330DHCX over SPI.

    Manages SPI and GPIO resources for the lifetime of the ``with`` block.
    On entry the IMU is reset and configured; on exit all resources are
    released. Two consumption patterns are supported:

    Continuous iteration (recommended for server backends)::

        with IMUReader() as imu:
            for sample in imu:
                process(sample)

    Single read (useful for one-shot or polling scenarios)::

        with IMUReader() as imu:
            sample = imu.read()

    Args:
        gpio_chip: Path to the GPIO chip device (default: ``/dev/gpiochip4``).
        gpio_line: GPIO line number for the DRDY interrupt pin (default: 25).
        spi_bus: SPI bus number (default: 0).
        spi_device: SPI chip-select number (default: 0).
    """

    def __init__(
        self,
        gpio_chip: str = _GPIO_CHIP,
        gpio_line: int = _GPIO_LINE,
        spi_bus: int = _SPI_BUS,
        spi_device: int = _SPI_DEVICE,
    ) -> None:
        """Store hardware parameters; resources are opened in __enter__."""
        self._gpio_chip = gpio_chip
        self._gpio_line = gpio_line
        self._spi_bus = spi_bus
        self._spi_device = spi_device
        self._spi: spidev.SpiDev | None = None
        self._chip: gpiod.Chip | None = None
        self._request: gpiod.LineRequest | None = None

    def __enter__(self) -> "IMUReader":
        """Open SPI, reset the IMU, set up GPIO edge detection, and start sampling."""
        self._spi = spidev.SpiDev()
        self._spi.open(self._spi_bus, self._spi_device)
        self._spi.max_speed_hz = _SPI_MAX_SPEED_HZ
        self._spi.mode = 0

        # Reset before setting up GPIO so no spurious edges are missed
        _reset_imu(self._spi)

        settings = gpiod.LineSettings(
            direction=Direction.INPUT,
            edge_detection=Edge.RISING,
        )
        self._chip = gpiod.Chip(self._gpio_chip)
        self._request = self._chip.request_lines(
            consumer="IMUReader",
            config={self._gpio_line: settings},
        )

        # GPIO edge detection is active; safe to start the measurement cycle
        _start_imu(self._spi)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Release GPIO line, close chip, and close SPI."""
        if self._request is not None:
            self._request.release()
            self._request = None
        if self._chip is not None:
            self._chip.close()
            self._chip = None
        if self._spi is not None:
            self._spi.close()
            self._spi = None

    def read(self, timeout: float = 1.0) -> IMUData:
        """Block until the next DRDY interrupt and return one IMU sample.

        Args:
            timeout: Maximum seconds to wait for a rising edge on the DRDY
                pin. Raises ``TimeoutError`` if no edge arrives in time.

        Returns:
            IMUData with physical-unit accelerometer and gyroscope values.

        Raises:
            RuntimeError: If called outside a ``with`` block.
            TimeoutError: If no DRDY interrupt fires within *timeout* seconds.
        """
        if self._request is None or self._spi is None:
            raise RuntimeError("IMUReader must be used as a context manager.")
        if not self._request.wait_edge_events(timeout=timeout):
            raise TimeoutError(f"No IMU DRDY interrupt within {timeout}s.")
        self._request.read_edge_events()
        ts = time.clock_gettime(time.CLOCK_REALTIME)
        return _read_sample(self._spi, ts)

    def __iter__(self) -> Iterator[IMUData]:
        """Yield IMU samples indefinitely, one per DRDY interrupt.

        Iteration continues until a ``TimeoutError`` propagates out or the
        caller breaks the loop. ``StopIteration`` is never raised.

        Yields:
            IMUData for each DRDY edge.
        """
        while True:
            yield self.read()
