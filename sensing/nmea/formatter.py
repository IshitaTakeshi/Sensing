"""GGA sentence formatter: serialize GGAData to a NMEA 0183 sentence."""

from functools import reduce

from sensing.nmea.types import GGAData

__all__ = ["format_gga"]


def _xor_checksum(payload: str) -> str:
    """Return the two-digit uppercase hex XOR checksum of payload."""
    value = reduce(lambda acc, c: acc ^ ord(c), payload, 0)
    return f"{value:02X}"


def _degrees_to_nmea(decimal: float, *, is_latitude: bool) -> tuple[str, str]:
    """Convert decimal degrees to NMEA DDMM.MMMM / DDDMM.MMMM and hemisphere char."""
    abs_deg = abs(decimal)
    degrees = int(abs_deg)
    minutes = (abs_deg - degrees) * 60.0
    if is_latitude:
        return f"{degrees:02d}{minutes:07.4f}", "N" if decimal >= 0 else "S"
    return f"{degrees:03d}{minutes:07.4f}", "E" if decimal >= 0 else "W"


def _opt_float(value: float | None, fmt: str) -> str:
    """Format a float with fmt, or return an empty string if None."""
    if value is None:
        return ""
    return format(value, fmt)


def format_gga(gga: GGAData) -> str:
    r"""Serialize a GGAData to a valid NMEA $GPGGA sentence.

    Returns a complete sentence terminated with ``\r\n``, including checksum.

    Args:
        gga: GNSS fix data to serialize.

    Returns:
        NMEA sentence e.g. ``"$GPGGA,123519.00,3539.5160,N,13944.7240,E,...*XX\r\n"``.

    Raises:
        ValueError: If ``latitude_degrees`` or ``longitude_degrees`` is ``None``.
    """
    if gga.latitude_degrees is None or gga.longitude_degrees is None:
        raise ValueError("Cannot format GGA without valid coordinates.")
    lat, lat_dir = _degrees_to_nmea(gga.latitude_degrees, is_latitude=True)
    lon, lon_dir = _degrees_to_nmea(gga.longitude_degrees, is_latitude=False)
    utc = gga.utc_time or ""
    num_sats = "" if gga.num_satellites is None else str(gga.num_satellites)
    hdop = _opt_float(gga.horizontal_dilution_of_precision, ".1f")
    alt = _opt_float(gga.altitude_meters, ".1f")
    geoid = _opt_float(gga.geoid_height_meters, ".1f")
    payload = (
        f"GPGGA,{utc},{lat},{lat_dir},{lon},{lon_dir},"
        f"{gga.fix_quality},{num_sats},{hdop},{alt},M,{geoid},M,,"
    )
    return f"${payload}*{_xor_checksum(payload)}\r\n"
