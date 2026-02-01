"""Tests for GGA sentence parsing."""

import pytest

from sensing import parse_gga


class TestParseGGA:
    """Tests for parse_gga function."""

    def test_valid_gga_with_fix(self):
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*7F"
        result = parse_gga(sentence)
        assert result is not None
        assert result.utc_time == "123519.00"
        assert result.latitude_deg == pytest.approx(48.1173, rel=1e-4)
        assert result.longitude_deg == pytest.approx(11.5166667, rel=1e-4)
        assert result.fix_quality == 1
        assert result.num_satellites == 8
        assert result.hdop == pytest.approx(0.9)
        assert result.altitude_m == pytest.approx(545.4)
        assert result.geoid_height_m == pytest.approx(47.0)
        assert result.valid is True

    def test_gga_no_fix(self):
        sentence = "$GNGGA,123519.00,,,,,0,00,,,,,,,*5B"
        result = parse_gga(sentence)
        assert result is not None
        assert result.utc_time == "123519.00"
        assert result.latitude_deg is None
        assert result.longitude_deg is None
        assert result.fix_quality == 0
        assert result.num_satellites == 0
        assert result.hdop is None
        assert result.altitude_m is None
        assert result.geoid_height_m is None
        assert result.valid is False

    def test_gga_empty_fields_with_fix(self):
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,1,,,545.4,M,,M,,*4D"
        result = parse_gga(sentence)
        assert result is not None
        assert result.fix_quality == 1
        assert result.num_satellites is None and result.hdop is None
        assert result.altitude_m == pytest.approx(545.4)

    def test_gga_southern_hemisphere(self):
        sentence = "$GPGGA,123519.00,3356.123,S,15112.456,W,2,10,0.8,100.0,M,20.0,M,,*65"
        result = parse_gga(sentence)
        assert result is not None
        assert result.latitude_deg == pytest.approx(-33.93538333, rel=1e-4)
        assert result.longitude_deg == pytest.approx(-151.20760, rel=1e-4)

    def test_gga_rtk_fixed(self):
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,4,12,0.5,545.4,M,47.0,M,,*7D"
        assert parse_gga(sentence) is not None

    def test_gga_rtk_float(self):
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,5,12,0.6,545.4,M,47.0,M,,*7F"
        assert parse_gga(sentence) is not None

    def test_gga_invalid_checksum(self):
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*FF"
        assert parse_gga(sentence) is None

    def test_gga_malformed_too_few_fields(self):
        assert parse_gga("$GNGGA,123519.00,4807.038,N*12") is None

    def test_gga_wrong_sentence_type(self):
        assert parse_gga("$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,A*3B") is None

    def test_gga_invalid_prefix(self):
        sentence = "$XXGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*76"
        assert parse_gga(sentence) is None

    def test_gga_empty_fix_quality_defaults_to_zero(self):
        result = parse_gga("$GNGGA,123519.00,,,,,,,,,,,,,*6B")
        assert result is not None and result.fix_quality == 0

    def test_gga_multi_constellation_prefixes(self):
        prefixes = [("GP", "61"), ("GN", "7F"), ("GL", "7D"),
                    ("GA", "70"), ("GB", "73"), ("GQ", "60")]
        for prefix, cs in prefixes:
            s = f"${prefix}GGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*{cs}"
            assert parse_gga(s) is not None, f"Failed: {prefix}"

    def test_gga_trailing_whitespace(self):
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*7F   \n"
        assert parse_gga(sentence) is not None

    def test_gga_high_precision_coordinates(self):
        sentence = "$GNGGA,123519.00,4807.03812345,N,01131.00098765,E,4,12,0.5,545.4,M,47.0,M,,*79"
        result = parse_gga(sentence)
        assert result is not None
        assert result.latitude_deg == pytest.approx(48.11730208, rel=1e-6)
        assert result.longitude_deg == pytest.approx(11.51668313, rel=1e-6)

    def test_zedf9p_gga_rtk_fixed(self):
        sentence = "$GNGGA,081836.00,3723.46587,N,12202.26957,W,4,12,0.7,10.5,M,-30.0,M,1.0,0000*51"
        assert parse_gga(sentence) is not None
