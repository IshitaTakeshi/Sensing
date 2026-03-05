"""NTRIP client configuration dataclass."""

from dataclasses import dataclass

__all__ = ["NTRIPConfig"]


@dataclass(frozen=True)
class NTRIPConfig:
    """Immutable configuration for an NTRIP caster connection.

    Args:
        host: NTRIP caster hostname or IP address.
        port: NTRIP caster TCP port.
        mountpoint: NTRIP mountpoint name.
        serial_device: Path to the serial device for RTCM3 output.
        username: Username for Basic Auth (default: empty -- no auth).
        password: Password for Basic Auth (default: empty -- no auth).
    """

    host: str
    port: int
    mountpoint: str
    serial_device: str
    username: str = ""
    password: str = ""
    gga_interval_seconds: float = 10.0
