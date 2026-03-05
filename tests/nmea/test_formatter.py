"""Tests for the NMEA GGA sentence formatter."""

import pytest

from sensing.nmea.checksum import validate_checksum
from sensing.nmea.formatter import format_gga
from sensing.nmea.gga import parse_gga
from sensing.nmea.types import GGAData

# Tokyo Tower — public landmark used to avoid privacy-sensitive coordinates.
_LAT = 35.6586
_LON = 139.7454

_GGA = GGAData(
    utc_time="123519.00",
    latitude_degrees=_LAT,
    longitude_degrees=_LON,
    fix_quality=4,
    num_satellites=12,
    horizontal_dilution_of_precision=0.5,
    altitude_meters=333.0,
    geoid_height_meters=36.6,
    valid=True,
)


class TestFormatGga:
    def test_output_has_valid_nmea_checksum(self):
        sentence = format_gga(_GGA).strip()
        assert validate_checksum(sentence)

    def test_output_starts_with_dollar_gpgga(self):
        assert format_gga(_GGA).startswith("$GPGGA,")

    def test_output_ends_with_crlf(self):
        assert format_gga(_GGA).endswith("\r\n")

    def test_round_trip_latitude(self):
        sentence = format_gga(_GGA).strip()
        result = parse_gga(sentence)
        assert result is not None
        assert result.latitude_degrees == pytest.approx(_LAT, rel=1e-5)

    def test_round_trip_longitude(self):
        sentence = format_gga(_GGA).strip()
        result = parse_gga(sentence)
        assert result is not None
        assert result.longitude_degrees == pytest.approx(_LON, rel=1e-5)

    def test_round_trip_fix_quality(self):
        sentence = format_gga(_GGA).strip()
        result = parse_gga(sentence)
        assert result is not None
        assert result.fix_quality == 4

    def test_southern_hemisphere_uses_s(self):
        gga = GGAData(
            utc_time=None, latitude_degrees=-35.6586, longitude_degrees=_LON,
            fix_quality=1, num_satellites=None, horizontal_dilution_of_precision=None,
            altitude_meters=None, geoid_height_meters=None, valid=True,
        )
        assert ",S," in format_gga(gga)

    def test_western_hemisphere_uses_w(self):
        gga = GGAData(
            utc_time=None, latitude_degrees=_LAT, longitude_degrees=-139.7454,
            fix_quality=1, num_satellites=None, horizontal_dilution_of_precision=None,
            altitude_meters=None, geoid_height_meters=None, valid=True,
        )
        assert ",W," in format_gga(gga)

    def test_none_coordinates_raise_value_error(self):
        gga = GGAData(
            utc_time=None, latitude_degrees=None, longitude_degrees=_LON,
            fix_quality=0, num_satellites=None, horizontal_dilution_of_precision=None,
            altitude_meters=None, geoid_height_meters=None, valid=False,
        )
        with pytest.raises(ValueError, match="coordinates"):
            format_gga(gga)

    def test_none_optional_fields_produce_empty_nmea_fields(self):
        gga = GGAData(
            utc_time=None, latitude_degrees=_LAT, longitude_degrees=_LON,
            fix_quality=1, num_satellites=None, horizontal_dilution_of_precision=None,
            altitude_meters=None, geoid_height_meters=None, valid=True,
        )
        sentence = format_gga(gga)
        parsed = parse_gga(sentence.strip())
        assert parsed is not None
        assert parsed.num_satellites is None
        assert parsed.horizontal_dilution_of_precision is None
        assert parsed.altitude_meters is None
