"""NMEA 0183 parser for GGA and VTG sentences."""

from dataclasses import dataclass
from typing import Optional

# Multi-constellation prefixes: GPS, GLONASS, Galileo, BeiDou, QZSS, combined
VALID_PREFIXES = ("GP", "GN", "GL", "GA", "GB", "GQ")


@dataclass
class GGAData:
    """Parsed GGA (Global Positioning System Fix Data) sentence.

    Attributes:
        utc_time: UTC time in HHMMSS.sss format, None if empty.
        latitude_deg: Latitude in decimal degrees (positive=North), None if empty.
        longitude_deg: Longitude in decimal degrees (positive=East), None if empty.
        fix_quality: Fix quality indicator (0=invalid, 1=GPS, 2=DGPS, 4=RTK fixed,
            5=RTK float, 6=dead reckoning). Defaults to 0.
        num_satellites: Number of satellites in use, None if empty.
        hdop: Horizontal dilution of precision, None if empty.
        altitude_m: Altitude above mean sea level in meters, None if empty.
        geoid_height_m: Geoid separation in meters, None if empty.
        valid: True if fix_quality > 0 (navigation validity).
    """

    utc_time: Optional[str]
    latitude_deg: Optional[float]
    longitude_deg: Optional[float]
    fix_quality: int
    num_satellites: Optional[int]
    hdop: Optional[float]
    altitude_m: Optional[float]
    geoid_height_m: Optional[float]
    valid: bool


@dataclass
class VTGData:
    """Parsed VTG (Track Made Good and Ground Speed) sentence.

    Attributes:
        track_true_deg: Track angle in degrees (true north), None if empty.
        speed_knots: Ground speed in knots, None if empty.
        speed_kmh: Ground speed in km/h, None if empty.
        speed_mps: Ground speed in m/s (computed from kmh), None if kmh is empty.
        mode: FAA mode indicator (A=autonomous, D=differential, E=estimated,
            N=not valid), None if empty.
        valid: True if mode is not None and mode != 'N' (navigation validity).
    """

    track_true_deg: Optional[float]
    speed_knots: Optional[float]
    speed_kmh: Optional[float]
    speed_mps: Optional[float]
    mode: Optional[str]
    valid: bool


def validate_checksum(sentence: str) -> bool:
    """Validate NMEA sentence checksum.

    The checksum is the XOR of all bytes between '$' and '*' (exclusive).

    Args:
        sentence: NMEA sentence string (with or without trailing newline).

    Returns:
        True if checksum is valid, False otherwise.
    """
    sentence = sentence.strip()

    if not sentence.startswith("$") or "*" not in sentence:
        return False

    try:
        # Extract content between $ and *
        start = sentence.index("$") + 1
        end = sentence.index("*")
        content = sentence[start:end]

        # Extract provided checksum (2 hex digits after *)
        provided_checksum = sentence[end + 1 : end + 3]
        if len(provided_checksum) != 2:
            return False

        # Calculate XOR checksum
        calculated = 0
        for char in content:
            calculated ^= ord(char)

        return calculated == int(provided_checksum, 16)
    except (ValueError, IndexError):
        return False


def _parse_float(value: str) -> Optional[float]:
    """Parse a string to float, returning None if empty or invalid."""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_int(value: str) -> Optional[int]:
    """Parse a string to int, returning None if empty or invalid."""
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _convert_to_decimal_degrees(
    value: str, direction: str
) -> Optional[float]:
    """Convert NMEA lat/lon format (DDDMM.MMMM) to decimal degrees.

    Args:
        value: Coordinate in DDDMM.MMMM format.
        direction: N/S for latitude, E/W for longitude.

    Returns:
        Decimal degrees (positive for N/E, negative for S/W), or None if invalid.
    """
    if not value or not direction:
        return None

    try:
        # Find decimal point position to split degrees and minutes
        dot_pos = value.index(".")
        # Degrees are everything before the last 2 digits before decimal
        degrees = int(value[: dot_pos - 2])
        minutes = float(value[dot_pos - 2 :])
        decimal_degrees = degrees + minutes / 60.0

        if direction in ("S", "W"):
            decimal_degrees = -decimal_degrees

        return decimal_degrees
    except (ValueError, IndexError):
        return None


def parse_gga(sentence: str) -> Optional[GGAData]:
    """Parse a GGA (Global Positioning System Fix Data) sentence.

    Supports multi-constellation prefixes: GP, GN, GL, GA, GB, GQ.

    Args:
        sentence: NMEA GGA sentence string.

    Returns:
        GGAData if parsing succeeds, None if checksum fails or sentence is malformed.
    """
    sentence = sentence.strip()

    if not validate_checksum(sentence):
        return None

    try:
        # Remove checksum for parsing
        content = sentence[1 : sentence.index("*")]
        fields = content.split(",")

        # Validate sentence type
        msg_type = fields[0]
        if len(msg_type) < 5:
            return None

        prefix = msg_type[:2]
        suffix = msg_type[2:]

        if prefix not in VALID_PREFIXES or suffix != "GGA":
            return None

        # GGA has 14 or 15 fields (some receivers omit the last field)
        if len(fields) < 14:
            return None

        # Parse fields
        utc_time = fields[1] if fields[1] else None
        latitude_deg = _convert_to_decimal_degrees(fields[2], fields[3])
        longitude_deg = _convert_to_decimal_degrees(fields[4], fields[5])
        fix_quality = _parse_int(fields[6]) or 0
        num_satellites = _parse_int(fields[7])
        hdop = _parse_float(fields[8])
        altitude_m = _parse_float(fields[9])
        # fields[10] is altitude unit (M)
        geoid_height_m = _parse_float(fields[11])
        # fields[12] is geoid unit (M)
        # fields[13] is age of differential GPS data
        # fields[14] is differential reference station ID (may be absent)

        valid = fix_quality > 0

        return GGAData(
            utc_time=utc_time,
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            fix_quality=fix_quality,
            num_satellites=num_satellites,
            hdop=hdop,
            altitude_m=altitude_m,
            geoid_height_m=geoid_height_m,
            valid=valid,
        )
    except (ValueError, IndexError):
        return None


def parse_vtg(sentence: str) -> Optional[VTGData]:
    """Parse a VTG (Track Made Good and Ground Speed) sentence.

    Supports multi-constellation prefixes: GP, GN, GL, GA, GB, GQ.

    Args:
        sentence: NMEA VTG sentence string.

    Returns:
        VTGData if parsing succeeds, None if checksum fails or sentence is malformed.
    """
    sentence = sentence.strip()

    if not validate_checksum(sentence):
        return None

    try:
        # Remove checksum for parsing
        content = sentence[1 : sentence.index("*")]
        fields = content.split(",")

        # Validate sentence type
        msg_type = fields[0]
        if len(msg_type) < 5:
            return None

        prefix = msg_type[:2]
        suffix = msg_type[2:]

        if prefix not in VALID_PREFIXES or suffix != "VTG":
            return None

        # VTG has 9 or 10 fields
        if len(fields) < 9:
            return None

        # Parse fields
        track_true_deg = _parse_float(fields[1])
        # fields[2] is 'T' (true)
        # fields[3] is track magnetic (optional)
        # fields[4] is 'M' (magnetic)
        speed_knots = _parse_float(fields[5])
        # fields[6] is 'N' (knots)
        speed_kmh = _parse_float(fields[7])
        # fields[8] is 'K' (km/h)

        # Mode indicator (FAA) - may be in field 9 or absent in older receivers
        mode: Optional[str] = None
        if len(fields) > 9 and fields[9]:
            mode = fields[9]

        # Compute speed in m/s from km/h
        speed_mps: Optional[float] = None
        if speed_kmh is not None:
            speed_mps = speed_kmh / 3.6

        valid = mode is not None and mode != "N"

        return VTGData(
            track_true_deg=track_true_deg,
            speed_knots=speed_knots,
            speed_kmh=speed_kmh,
            speed_mps=speed_mps,
            mode=mode,
            valid=valid,
        )
    except (ValueError, IndexError):
        return None
