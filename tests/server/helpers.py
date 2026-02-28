"""Helper factories for server tests."""

from sensing.gnss import GNSSData
from sensing.nmea.types import GGAData, VTGData


def make_gga() -> GGAData:
    return GGAData(
        utc_time="120000.00",
        latitude_degrees=45.0,
        longitude_degrees=9.0,
        fix_quality=1,
        num_satellites=8,
        horizontal_dilution_of_precision=1.0,
        altitude_meters=100.0,
        geoid_height_meters=50.0,
        valid=True,
    )


def make_gnss(has_vtg: bool, vtg_valid: bool) -> GNSSData:
    vtg_data = None
    if has_vtg:
        vtg_data = VTGData(
            track_true_degrees=12.3,
            speed_knots=4.5,
            speed_kilometers_per_hour=8.3,
            speed_meters_per_second=2.3,
            mode="A" if vtg_valid else "N",
            valid=vtg_valid,
        )
    return GNSSData(gga=make_gga(), vtg=vtg_data)
