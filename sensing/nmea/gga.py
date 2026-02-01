"""GGA sentence parser."""


from sensing.nmea.checksum import validate_checksum
from sensing.nmea.fields import (
    VALID_TALKER_IDS,
    convert_to_decimal_degrees,
    parse_float_field,
    parse_int_field,
    parse_string_field,
)
from sensing.nmea.types import GGAData

_MINIMUM_FIELD_COUNT = 14


def _extract_fields(sentence: str) -> list[str] | None:
    """Extract fields from validated GGA sentence."""
    content = sentence[1 : sentence.index("*")]
    fields = content.split(",")

    if len(fields) < _MINIMUM_FIELD_COUNT:
        return None

    return fields


def _validate_message_type(fields: list[str]) -> bool:
    """Validate GGA message type and talker ID."""
    message_type = fields[0]
    if len(message_type) < 5:
        return False

    talker_id = message_type[:2]
    sentence_type = message_type[2:]

    return talker_id in VALID_TALKER_IDS and sentence_type == "GGA"


def _build_gga_data(fields: list[str]) -> GGAData:
    """Build GGAData from parsed fields."""
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
        valid=fix_quality > 0,
    )


def parse_gga(sentence: str) -> GGAData | None:
    """Parse a GGA sentence into structured data."""
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
