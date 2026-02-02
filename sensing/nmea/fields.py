"""NMEA field parsing utilities.

This module provides utilities for parsing individual fields from NMEA sentences.
NMEA fields are comma-separated and may be empty (consecutive commas indicate
missing data). These utilities handle empty fields gracefully by returning None,
allowing callers to distinguish "no data" from "zero value".
"""


# Supported NMEA talker IDs for multi-constellation GNSS receivers.
# Each 2-character prefix identifies the satellite system:
#   GP = GPS (USA)
#   GN = Multi-GNSS (combined solution)
#   GL = GLONASS (Russia)
#   GA = Galileo (Europe)
#   GB = BeiDou (China)
#   GQ = QZSS (Japan)
VALID_TALKER_IDS = ("GP", "GN", "GL", "GA", "GB", "GQ")


def parse_float_field(value: str) -> float | None:
    """Parse a string field to float, returning None if empty or invalid.

    NMEA fields may be empty (indicated by consecutive commas like ",,").
    This function treats empty strings as "no data" rather than an error.

    Args:
        value: String value from an NMEA field

    Returns:
        Parsed float value, or None if the field is empty or unparseable

    Example:
        >>> parse_float_field("545.4")
        545.4
        >>> parse_float_field("")  # empty field
        None
    """
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_int_field(value: str) -> int | None:
    """Parse a string field to int, returning None if empty or invalid.

    Similar to parse_float_field but for integer values like satellite count
    or fix quality indicators.

    Args:
        value: String value from an NMEA field

    Returns:
        Parsed integer value, or None if the field is empty or unparseable

    Example:
        >>> parse_int_field("08")
        8
        >>> parse_int_field("")
        None
    """
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_string_field(value: str) -> str | None:
    """Parse a string field, returning None if empty.

    Used for fields like UTC time or mode indicators where the raw string
    value is meaningful.

    Args:
        value: String value from an NMEA field

    Returns:
        The string value unchanged, or None if empty

    Example:
        >>> parse_string_field("123519.00")
        '123519.00'
        >>> parse_string_field("")
        None
    """
    if not value:
        return None
    return value


def _parse_coordinate_parts(value: str) -> tuple[int, float] | None:
    """Parse NMEA coordinate into degrees and minutes components.

    NMEA coordinates use DDDMM.MMMM format where:
    - DDD (or DD for latitude) = degrees
    - MM.MMMM = decimal minutes

    The decimal point position determines the split between degrees and minutes:
    the 2 digits before the decimal point are always minutes.

    Args:
        value: Coordinate string in DDDMM.MMMM format

    Returns:
        Tuple of (degrees, minutes) or None if parsing fails

    Example:
        >>> _parse_coordinate_parts("4807.038")  # 48° 07.038'
        (48, 7.038)
        >>> _parse_coordinate_parts("01131.000")  # 11° 31.000'
        (11, 31.0)
    """
    try:
        dot_position = value.index(".")
        # Minutes are always 2 digits before the decimal point
        degrees = int(value[: dot_position - 2])
        minutes = float(value[dot_position - 2 :])
        return degrees, minutes
    except (ValueError, IndexError):
        return None


def convert_to_decimal_degrees(
    value: str,
    direction: str,
) -> float | None:
    """Convert NMEA coordinate (DDDMM.MMMM) to decimal degrees.

    NMEA uses degrees-minutes format with a hemisphere indicator.
    This function converts to decimal degrees with sign convention:
    - North/East = positive
    - South/West = negative

    The conversion formula is:
        decimal_degrees = degrees + (minutes / 60)

    Args:
        value: Coordinate in DDDMM.MMMM format (e.g., "4807.038")
        direction: Hemisphere indicator ("N", "S", "E", or "W")

    Returns:
        Decimal degrees (positive for N/E, negative for S/W),
        or None if either field is empty

    Example:
        >>> convert_to_decimal_degrees("4807.038", "N")
        48.1173  # 48° + 7.038'/60
        >>> convert_to_decimal_degrees("01131.000", "W")
        -11.5166667  # negative for West
    """
    if not value or not direction:
        return None

    parts = _parse_coordinate_parts(value)
    if parts is None:
        return None

    degrees, minutes = parts
    decimal_degrees = degrees + minutes / 60.0

    if direction in ("S", "W"):
        return -decimal_degrees

    return decimal_degrees
