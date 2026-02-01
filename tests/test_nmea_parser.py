"""Unit tests for NMEA parser."""

import pytest

from sensing import (
    parse_gga,
    parse_vtg,
    validate_checksum,
)


class TestValidateChecksum:
    """Tests for validate_checksum function."""

    def test_valid_checksum(self):
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*7F"
        assert validate_checksum(sentence) is True

    def test_valid_checksum_with_newline(self):
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*7F\r\n"
        assert validate_checksum(sentence) is True

    def test_invalid_checksum(self):
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*FF"
        assert validate_checksum(sentence) is False

    def test_missing_dollar_sign(self):
        sentence = "GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*7F"
        assert validate_checksum(sentence) is False

    def test_missing_asterisk(self):
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,7F"
        assert validate_checksum(sentence) is False

    def test_empty_string(self):
        assert validate_checksum("") is False

    def test_truncated_checksum(self):
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*7"
        assert validate_checksum(sentence) is False

    def test_vtg_checksum(self):
        sentence = "$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,A*3B"
        assert validate_checksum(sentence) is True


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
        """Test GGA with fix but some optional fields empty."""
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,1,,,545.4,M,,M,,*4D"
        result = parse_gga(sentence)

        assert result is not None
        assert result.fix_quality == 1
        assert result.num_satellites is None
        assert result.hdop is None
        assert result.altitude_m == pytest.approx(545.4)
        assert result.geoid_height_m is None
        assert result.valid is True

    def test_gga_southern_hemisphere(self):
        sentence = "$GPGGA,123519.00,3356.123,S,15112.456,W,2,10,0.8,100.0,M,20.0,M,,*65"
        result = parse_gga(sentence)

        assert result is not None
        assert result.latitude_deg == pytest.approx(-33.93538333, rel=1e-4)
        assert result.longitude_deg == pytest.approx(-151.20760, rel=1e-4)
        assert result.fix_quality == 2
        assert result.valid is True

    def test_gga_rtk_fixed(self):
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,4,12,0.5,545.4,M,47.0,M,,*7D"
        result = parse_gga(sentence)

        assert result is not None
        assert result.fix_quality == 4
        assert result.valid is True

    def test_gga_rtk_float(self):
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,5,12,0.6,545.4,M,47.0,M,,*7F"
        result = parse_gga(sentence)

        assert result is not None
        assert result.fix_quality == 5
        assert result.valid is True

    def test_gga_invalid_checksum(self):
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*FF"
        result = parse_gga(sentence)

        assert result is None

    def test_gga_malformed_too_few_fields(self):
        sentence = "$GNGGA,123519.00,4807.038,N*12"
        result = parse_gga(sentence)

        assert result is None

    def test_gga_wrong_sentence_type(self):
        sentence = "$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,A*3B"
        result = parse_gga(sentence)

        assert result is None

    def test_gga_multi_constellation_prefixes(self):
        """Test all valid constellation prefixes."""
        prefixes_and_checksums = [
            ("GP", "61"),
            ("GN", "7F"),
            ("GL", "7D"),
            ("GA", "70"),
            ("GB", "73"),
            ("GQ", "60"),
        ]

        for prefix, checksum in prefixes_and_checksums:
            sentence = f"${prefix}GGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*{checksum}"
            result = parse_gga(sentence)
            assert result is not None, f"Failed for prefix {prefix}"
            assert result.valid is True

    def test_gga_invalid_prefix(self):
        sentence = "$XXGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*76"
        result = parse_gga(sentence)

        assert result is None

    def test_gga_empty_fix_quality_defaults_to_zero(self):
        """Empty fix_quality should default to 0, not None."""
        sentence = "$GNGGA,123519.00,,,,,,,,,,,,,*6B"
        result = parse_gga(sentence)

        assert result is not None
        assert result.fix_quality == 0
        assert result.valid is False


class TestParseVTG:
    """Tests for parse_vtg function."""

    def test_valid_vtg_autonomous(self):
        sentence = "$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,A*3B"
        result = parse_vtg(sentence)

        assert result is not None
        assert result.track_true_deg == pytest.approx(54.7)
        assert result.speed_knots == pytest.approx(5.5)
        assert result.speed_kmh == pytest.approx(10.2)
        assert result.speed_mps == pytest.approx(10.2 / 3.6)
        assert result.mode == "A"
        assert result.valid is True

    def test_vtg_differential_mode(self):
        sentence = "$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,D*3E"
        result = parse_vtg(sentence)

        assert result is not None
        assert result.mode == "D"
        assert result.valid is True

    def test_vtg_not_valid_mode(self):
        sentence = "$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,N*34"
        result = parse_vtg(sentence)

        assert result is not None
        assert result.mode == "N"
        assert result.valid is False

    def test_vtg_stationary_empty_track(self):
        """When stationary, track should be None (not 0.0)."""
        sentence = "$GNVTG,,T,,M,0.0,N,0.0,K,A*3D"
        result = parse_vtg(sentence)

        assert result is not None
        assert result.track_true_deg is None
        assert result.speed_knots == pytest.approx(0.0)
        assert result.speed_kmh == pytest.approx(0.0)
        assert result.speed_mps == pytest.approx(0.0)
        assert result.mode == "A"
        assert result.valid is True

    def test_vtg_all_empty_fields(self):
        sentence = "$GNVTG,,T,,M,,N,,K,N*32"
        result = parse_vtg(sentence)

        assert result is not None
        assert result.track_true_deg is None
        assert result.speed_knots is None
        assert result.speed_kmh is None
        assert result.speed_mps is None
        assert result.mode == "N"
        assert result.valid is False

    def test_vtg_no_mode_indicator(self):
        """Older receivers may not include mode indicator."""
        sentence = "$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K*56"
        result = parse_vtg(sentence)

        assert result is not None
        assert result.track_true_deg == pytest.approx(54.7)
        assert result.mode is None
        assert result.valid is False  # No mode = not valid

    def test_vtg_invalid_checksum(self):
        sentence = "$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,A*FF"
        result = parse_vtg(sentence)

        assert result is None

    def test_vtg_malformed_too_few_fields(self):
        sentence = "$GNVTG,054.7,T*12"
        result = parse_vtg(sentence)

        assert result is None

    def test_vtg_wrong_sentence_type(self):
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*7F"
        result = parse_vtg(sentence)

        assert result is None

    def test_vtg_multi_constellation_prefixes(self):
        """Test all valid constellation prefixes."""
        prefixes_and_checksums = [
            ("GP", "25"),
            ("GN", "3B"),
            ("GL", "39"),
            ("GA", "34"),
            ("GB", "37"),
            ("GQ", "24"),
        ]

        for prefix, checksum in prefixes_and_checksums:
            sentence = f"${prefix}VTG,054.7,T,034.4,M,005.5,N,010.2,K,A*{checksum}"
            result = parse_vtg(sentence)
            assert result is not None, f"Failed for prefix {prefix}"
            assert result.valid is True

    def test_vtg_invalid_prefix(self):
        sentence = "$XXVTG,054.7,T,034.4,M,005.5,N,010.2,K,A*32"
        result = parse_vtg(sentence)

        assert result is None

    def test_vtg_speed_mps_computed_correctly(self):
        """Verify m/s is correctly computed from km/h."""
        sentence = "$GNVTG,000.0,T,000.0,M,000.0,N,036.0,K,A*38"
        result = parse_vtg(sentence)

        assert result is not None
        assert result.speed_kmh == pytest.approx(36.0)
        assert result.speed_mps == pytest.approx(10.0)  # 36 / 3.6 = 10

    def test_vtg_speed_mps_none_when_kmh_empty(self):
        """speed_mps should be None when speed_kmh is empty."""
        sentence = "$GNVTG,054.7,T,034.4,M,005.5,N,,K,A*16"
        result = parse_vtg(sentence)

        assert result is not None
        assert result.speed_kmh is None
        assert result.speed_mps is None


class TestRealZEDF9POutput:
    """Tests with real ZED-F9P receiver output samples."""

    def test_zedf9p_gga_rtk_fixed(self):
        """Real ZED-F9P GGA with RTK fixed solution."""
        sentence = "$GNGGA,081836.00,3723.46587,N,12202.26957,W,4,12,0.7,10.5,M,-30.0,M,1.0,0000*51"
        result = parse_gga(sentence)

        assert result is not None
        assert result.fix_quality == 4
        assert result.num_satellites == 12
        assert result.valid is True

    def test_zedf9p_vtg_moving(self):
        """Real ZED-F9P VTG while moving."""
        sentence = "$GNVTG,325.5,T,337.8,M,0.5,N,0.9,K,D*3A"
        result = parse_vtg(sentence)

        assert result is not None
        assert result.mode == "D"
        assert result.valid is True


class TestEdgeCases:
    """Edge case tests."""

    def test_gga_with_trailing_whitespace(self):
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*7F   \n"
        result = parse_gga(sentence)

        assert result is not None
        assert result.valid is True

    def test_vtg_with_crlf(self):
        sentence = "$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,A*3B\r\n"
        result = parse_vtg(sentence)

        assert result is not None
        assert result.valid is True

    def test_gga_high_precision_coordinates(self):
        """Test high precision coordinate parsing (8 decimal places in minutes)."""
        sentence = "$GNGGA,123519.00,4807.03812345,N,01131.00098765,E,4,12,0.5,545.4,M,47.0,M,,*79"
        result = parse_gga(sentence)

        assert result is not None
        # 48 + 7.03812345/60 = 48.117302...
        assert result.latitude_deg == pytest.approx(48.11730208, rel=1e-6)
        # 11 + 31.00098765/60 = 11.51668...
        assert result.longitude_deg == pytest.approx(11.51668313, rel=1e-6)
