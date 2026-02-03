"""VTG sentence parser.

VTG (Track Made Good and Ground Speed) provides velocity information from GNSS.
This is essential for navigation and sensor fusion applications that need
ground speed and heading data.

VTG Sentence Format:
    $GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,A*3B
           |     | |     | |     | |     | |
           |     | |     | |     | |     | +-- Mode indicator (A/D/E/N)
           |     | |     | |     | +-----+-- Speed in km/h
           |     | |     | +-----+-- Speed in knots
           |     | +-----+-- Track (magnetic north, degrees)
           +-----+-- Track (true north, degrees)

Mode Indicators (FAA mode, NMEA 2.3+):
    A = Autonomous (standard GPS positioning)
    D = Differential (DGPS or RTK)
    E = Estimated (dead reckoning)
    N = Not valid (no fix)

Note: When stationary, the track angle may be empty (no heading when not moving).
"""


from sensing.nmea.checksum import validate_checksum
from sensing.nmea.fields import (
    VALID_TALKER_IDS,
    parse_float_field,
    parse_string_field,
)
from sensing.nmea.types import VTGData

# VTG has 9 fields in basic format, 10 with FAA mode indicator
_MINIMUM_FIELD_COUNT = 9

# Conversion factor: km/h to m/s
# 1 km/h = 1000m / 3600s = 1/3.6 m/s
_KILOMETERS_PER_HOUR_TO_METERS_PER_SECOND = 3.6


def _extract_fields(sentence: str) -> list[str] | None:
    """Extract comma-separated fields from a validated VTG sentence.

    Assumes the sentence has already passed checksum validation.
    Extracts the content between '$' and '*', then splits by comma.

    Args:
        sentence: Checksum-validated NMEA sentence

    Returns:
        List of field strings, or None if fewer than 9 fields
        (indicating a malformed or truncated sentence)

    Example:
        Input: "$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,A*3B"
        Output: ["GNVTG", "054.7", "T", "034.4", "M", "005.5", "N", "010.2", "K", "A"]
    """
    content = sentence[1 : sentence.index("*")]
    fields = content.split(",")

    if len(fields) < _MINIMUM_FIELD_COUNT:
        return None

    return fields


def _validate_message_type(fields: list[str]) -> bool:
    """Validate that this is a VTG sentence from a supported constellation.

    Checks that:
    1. The message type field has at least 5 characters (2 talker + 3 sentence)
    2. The talker ID is a supported GNSS constellation
    3. The sentence type is "VTG"

    Args:
        fields: List of parsed NMEA fields

    Returns:
        True if valid VTG from supported constellation, False otherwise

    Example:
        fields[0] = "GNVTG" -> talker="GN", sentence="VTG" -> True
        fields[0] = "GNGGA" -> sentence="GGA" (not VTG) -> False
    """
    message_type = fields[0]
    if len(message_type) < 5:
        return False

    talker_id = message_type[:2]
    sentence_type = message_type[2:]

    return talker_id in VALID_TALKER_IDS and sentence_type == "VTG"


def _extract_mode(fields: list[str]) -> str | None:
    """Extract the FAA mode indicator from VTG fields.

    The mode indicator was added in NMEA 2.3 and appears at index 9.
    Older receivers may not include this field.

    Mode values:
        A = Autonomous (standard GPS)
        D = Differential (DGPS, RTK)
        E = Estimated (dead reckoning)
        N = Not valid

    Args:
        fields: List of parsed NMEA fields

    Returns:
        Single-character mode string, or None if field is missing/empty
    """
    if len(fields) <= 9:
        return None
    return parse_string_field(fields[9])


def _compute_speed_meters_per_second(
    speed_kilometers_per_hour: float | None,
) -> float | None:
    """Convert speed from km/h to m/s for sensor fusion compatibility.

    Many robotics and sensor fusion algorithms expect SI units (m/s).
    This derived value avoids repeated conversion in downstream code.

    Conversion: m/s = km/h ÷ 3.6

    Args:
        speed_kilometers_per_hour: Speed in km/h, or None if unavailable

    Returns:
        Speed in m/s, or None if input is None

    Example:
        >>> _compute_speed_meters_per_second(36.0)
        10.0  # 36 km/h = 10 m/s
    """
    if speed_kilometers_per_hour is None:
        return None
    return speed_kilometers_per_hour / _KILOMETERS_PER_HOUR_TO_METERS_PER_SECOND


def _build_vtg_data(fields: list[str]) -> VTGData:
    """Construct a VTGData object from parsed fields.

    Maps NMEA field indices to VTGData attributes:
        fields[1] -> track_true_degrees (heading relative to true north)
        fields[5] -> speed_knots
        fields[7] -> speed_kilometers_per_hour
        (computed) -> speed_meters_per_second (derived from km/h)
        fields[9] -> mode (FAA mode indicator, if present)

    Navigation validity is determined by the mode indicator:
    - valid=True if mode is A (autonomous) or D (differential)
    - valid=False if mode is N (not valid), E (estimated), or missing

    Args:
        fields: List of parsed NMEA fields (minimum 9 elements)

    Returns:
        VTGData with parsed values and computed validity
    """
    speed_kilometers_per_hour = parse_float_field(fields[7])
    mode = _extract_mode(fields)

    return VTGData(
        track_true_degrees=parse_float_field(fields[1]),
        speed_knots=parse_float_field(fields[5]),
        speed_kilometers_per_hour=speed_kilometers_per_hour,
        speed_meters_per_second=_compute_speed_meters_per_second(
            speed_kilometers_per_hour
        ),
        mode=mode,
        # Navigation validity: mode must exist and not be 'N' (not valid)
        valid=mode is not None and mode != "N",
    )


def parse_vtg(sentence: str) -> VTGData | None:
    """Parse a VTG sentence into structured data.

    This is the main entry point for VTG parsing. It performs:
    1. Whitespace stripping (handles \\r\\n line endings)
    2. Checksum validation
    3. Field extraction and count validation
    4. Message type validation (must be VTG from supported constellation)
    5. Field parsing and unit conversion

    Args:
        sentence: Raw NMEA VTG sentence string

    Returns:
        VTGData object if parsing succeeds, or None if:
        - Checksum is invalid
        - Sentence has too few fields
        - Message type is not VTG
        - Message is from unsupported constellation
        - Any parsing error occurs

    Note:
        A returned VTGData with valid=False indicates a successfully parsed
        sentence where the mode is 'N' (not valid) or missing. This is
        different from returning None, which indicates a malformed sentence.

    Example:
        >>> result = parse_vtg("$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,A*3B")
        >>> result.speed_meters_per_second
        2.833...
        >>> result.valid
        True
    """
    sentence = sentence.strip()

    if not validate_checksum(sentence):
        return None

    try:
        fields = _extract_fields(sentence)
        if fields is None:
            return None

        if not _validate_message_type(fields):
            return None

        return _build_vtg_data(fields)
    except (ValueError, IndexError):
        return None
