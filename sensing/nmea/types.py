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
    latitude_deg: float | None
    longitude_deg: float | None
    fix_quality: int
    num_satellites: int | None
    hdop: float | None
    altitude_m: float | None
    geoid_height_m: float | None
    valid: bool


@dataclass
class VTGData:
    """Parsed VTG (Track Made Good and Ground Speed) sentence.

    The valid field indicates navigation validity (mode not in None/'N'),
    not parse validity. A successfully parsed sentence with mode='N'
    will have valid=False.
    """

    track_true_deg: float | None
    speed_knots: float | None
    speed_kmh: float | None
    speed_mps: float | None
    mode: str | None
    valid: bool
