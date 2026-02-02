"""GGA sentence parser.

GGA (Global Positioning System Fix Data) is one of the most important NMEA
sentences, providing position fix information including coordinates, altitude,
fix quality, and satellite/accuracy metrics.

GGA Sentence Format:
    $GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*7F
           |         |        | |         | | |  |   |     | |     |
           |         |        | |         | | |  |   |     | |     +-- DGPS info (optional)
           |         |        | |         | | |  |   |     | +-- Geoid height (M=meters)
           |         |        | |         | | |  |   +-----+-- Altitude above MSL
           |         |        | |         | | |  +-- HDOP (horizontal dilution)
           |         |        | |         | | +-- Number of satellites
           |         |        | |         | +-- Fix quality (0-6)
           |         |        | +---------+-- Longitude + E/W
           |         +--------+-- Latitude + N/S
           +-- UTC time (HHMMSS.ss)

Fix Quality Values:
    0 = Invalid (no fix)
    1 = GPS fix (SPS - Standard Positioning Service)
    2 = DGPS fix (Differential GPS)
    4 = RTK Fixed (Real-Time Kinematic, cm-level accuracy)
    5 = RTK Float (RTK converging, dm-level accuracy)
    6 = Dead reckoning mode
"""


from sensing.nmea.checksum import validate_checksum
from sensing.nmea.fields import (
    VALID_TALKER_IDS,
    convert_to_decimal_degrees,
    parse_float_field,
    parse_int_field,
    parse_string_field,
)
from sensing.nmea.types import GGAData

# GGA sentences have 14 standard fields (indices 0-13)
# Some receivers add extra fields for DGPS station info
_MINIMUM_FIELD_COUNT = 14


def _extract_fields(sentence: str) -> list[str] | None:
    """Extract comma-separated fields from a validated GGA sentence.

    Assumes the sentence has already passed checksum validation.
    Extracts the content between '$' and '*', then splits by comma.

    Args:
        sentence: Checksum-validated NMEA sentence

    Returns:
        List of field strings, or None if fewer than 14 fields
        (indicating a malformed or truncated sentence)

    Example:
        Input: "$GNGGA,123519.00,4807.038,N,...*7F"
        Output: ["GNGGA", "123519.00", "4807.038", "N", ...]
    """
    content = sentence[1 : sentence.index("*")]
    fields = content.split(",")

    if len(fields) < _MINIMUM_FIELD_COUNT:
        return None

    return fields


def _validate_message_type(fields: list[str]) -> bool:
    """Validate that this is a GGA sentence from a supported constellation.

    Checks that:
    1. The message type field has at least 5 characters (2 talker + 3 sentence)
    2. The talker ID is a supported GNSS constellation
    3. The sentence type is "GGA"

    Args:
        fields: List of parsed NMEA fields

    Returns:
        True if valid GGA from supported constellation, False otherwise

    Example:
        fields[0] = "GNGGA" -> talker="GN", sentence="GGA" -> True
        fields[0] = "XXGGA" -> talker="XX" (unsupported) -> False
        fields[0] = "GNVTG" -> sentence="VTG" (not GGA) -> False
    """
    message_type = fields[0]
    if len(message_type) < 5:
        return False

    talker_id = message_type[:2]
    sentence_type = message_type[2:]

    return talker_id in VALID_TALKER_IDS and sentence_type == "GGA"


def _build_gga_data(fields: list[str]) -> GGAData:
    """Construct a GGAData object from parsed fields.

    Maps NMEA field indices to GGAData attributes:
        fields[1]  -> utc_time (HHMMSS.ss format)
        fields[2]  -> latitude (DDMM.MMMM format)
        fields[3]  -> latitude direction (N/S)
        fields[4]  -> longitude (DDDMM.MMMM format)
        fields[5]  -> longitude direction (E/W)
        fields[6]  -> fix_quality (0-6)
        fields[7]  -> num_satellites
        fields[8]  -> HDOP (horizontal dilution of precision)
        fields[9]  -> altitude above MSL (meters)
        fields[11] -> geoid height (meters)

    Note: fix_quality defaults to 0 (invalid) if the field is empty,
    since 0 already means "no fix" semantically.

    Args:
        fields: List of parsed NMEA fields (minimum 14 elements)

    Returns:
        GGAData with parsed values; valid=True only if fix_quality > 0
    """
    # Default fix_quality to 0 (invalid) if field is empty
    # This is semantically correct: empty fix quality means no fix
    fix_quality = parse_int_field(fields[6]) or 0

    return GGAData(
        utc_time=parse_string_field(fields[1]),
        latitude_degrees=convert_to_decimal_degrees(fields[2], fields[3]),
        longitude_degrees=convert_to_decimal_degrees(fields[4], fields[5]),
        fix_quality=fix_quality,
        num_satellites=parse_int_field(fields[7]),
        horizontal_dilution_of_precision=parse_float_field(fields[8]),
        altitude_meters=parse_float_field(fields[9]),
        geoid_height_meters=parse_float_field(fields[11]),
        # Navigation validity: only valid if we have a fix
        valid=fix_quality > 0,
    )


def parse_gga(sentence: str) -> GGAData | None:
    """Parse a GGA sentence into structured data.

    This is the main entry point for GGA parsing. It performs:
    1. Whitespace stripping (handles \\r\\n line endings)
    2. Checksum validation
    3. Field extraction and count validation
    4. Message type validation (must be GGA from supported constellation)
    5. Field parsing and coordinate conversion

    Args:
        sentence: Raw NMEA GGA sentence string

    Returns:
        GGAData object if parsing succeeds, or None if:
        - Checksum is invalid
        - Sentence has too few fields
        - Message type is not GGA
        - Message is from unsupported constellation
        - Any parsing error occurs

    Note:
        A returned GGAData with valid=False indicates a successfully parsed
        sentence that has no GPS fix (fix_quality=0). This is different from
        returning None, which indicates a malformed sentence.

    Example:
        >>> result = parse_gga("$GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*7F")
        >>> result.latitude_degrees
        48.1173
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

        return _build_gga_data(fields)
    except (ValueError, IndexError):
        return None
