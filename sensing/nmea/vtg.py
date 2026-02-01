"""VTG sentence parser."""


from sensing.nmea.checksum import validate_checksum
from sensing.nmea.fields import (
    VALID_TALKER_IDS,
    parse_float_field,
    parse_string_field,
)
from sensing.nmea.types import VTGData

_MINIMUM_FIELD_COUNT = 9
_KILOMETERS_PER_HOUR_TO_METERS_PER_SECOND = 3.6


def _extract_fields(sentence: str) -> list[str] | None:
    """Extract fields from validated VTG sentence."""
    content = sentence[1 : sentence.index("*")]
    fields = content.split(",")

    if len(fields) < _MINIMUM_FIELD_COUNT:
        return None

    return fields


def _validate_message_type(fields: list[str]) -> bool:
    """Validate VTG message type and talker ID."""
    message_type = fields[0]
    if len(message_type) < 5:
        return False

    talker_id = message_type[:2]
    sentence_type = message_type[2:]

    return talker_id in VALID_TALKER_IDS and sentence_type == "VTG"


def _extract_mode(fields: list[str]) -> str | None:
    """Extract FAA mode indicator from fields."""
    if len(fields) <= 9:
        return None
    return parse_string_field(fields[9])


def _compute_speed_meters_per_second(
    speed_kilometers_per_hour: float | None,
) -> float | None:
    """Compute speed in meters per second from kilometers per hour."""
    if speed_kilometers_per_hour is None:
        return None
    return speed_kilometers_per_hour / _KILOMETERS_PER_HOUR_TO_METERS_PER_SECOND


def _build_vtg_data(fields: list[str]) -> VTGData:
    """Build VTGData from parsed fields."""
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
        valid=mode is not None and mode != "N",
    )


def parse_vtg(sentence: str) -> VTGData | None:
    """Parse a VTG sentence into structured data."""
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
