"""NMEA data types for parsed sentences."""

from dataclasses import dataclass


@dataclass
class GGAData:
    """Parsed GGA (Global Positioning System Fix Data) sentence.

    The valid field indicates navigation validity (fix_quality > 0),
    not parse validity. A successfully parsed sentence with no fix
    will have valid=False.
    """

    utc_time: str | None
    latitude_degrees: float | None
    longitude_degrees: float | None
    fix_quality: int
    num_satellites: int | None
    horizontal_dilution_of_precision: float | None
    altitude_meters: float | None
    geoid_height_meters: float | None
    valid: bool


@dataclass
class VTGData:
    """Parsed VTG (Track Made Good and Ground Speed) sentence.

    The valid field indicates navigation validity (mode not in None/'N'),
    not parse validity. A successfully parsed sentence with mode='N'
    will have valid=False.
    """

    track_true_degrees: float | None
    speed_knots: float | None
    speed_kilometers_per_hour: float | None
    speed_meters_per_second: float | None
    mode: str | None
    valid: bool
