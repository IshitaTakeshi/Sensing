"""NMEA field parsing utilities."""


VALID_TALKER_IDS = ("GP", "GN", "GL", "GA", "GB", "GQ")


def parse_float_field(value: str) -> float | None:
    """Parse a string field to float, returning None if empty or invalid."""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_int_field(value: str) -> int | None:
    """Parse a string field to int, returning None if empty or invalid."""
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_string_field(value: str) -> str | None:
    """Parse a string field, returning None if empty."""
    if not value:
        return None
    return value


def _parse_coordinate_parts(value: str) -> tuple[int, float] | None:
    """Parse NMEA coordinate into degrees and minutes parts."""
    try:
        dot_position = value.index(".")
        degrees = int(value[: dot_position - 2])
        minutes = float(value[dot_position - 2 :])
        return degrees, minutes
    except (ValueError, IndexError):
        return None


def convert_to_decimal_degrees(
    value: str,
    direction: str,
) -> float | None:
    """Convert NMEA coordinate (DDDMM.MMMM) to decimal degrees."""
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
